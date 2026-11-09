"""Nordvet no-show pipeline: fetch from VetOne, load into DuckDB, build the
report views in SQL, check them and export them as Parquet for Power BI.

Run from the project folder:
    .venv\\Scripts\\python.exe pipeline\\run_pipeline.py                  daily run: the last 14 days up to today
    .venv\\Scripts\\python.exe pipeline\\run_pipeline.py --from 2026-08-06 backfill: everything from that date
    .venv\\Scripts\\python.exe pipeline\\run_pipeline.py --reload data\\raw\\run_20261107T120000Z
                                                                          load a saved run again, without the API

Steps:
  1. fetch   each API page is saved unchanged in data/raw/run_<UTC time>/
  2. load    the window's appointments in DuckDB are replaced by what the API returned
  3. sql     the views in pipeline/sql/ apply the rules and build the report tables
  4. check   simple data checks; a failed check stops the run before the export
  5. export  the report tables are written to data/export/*.parquet
Running it twice, or after a failed run, is safe: each run replaces the same window.
"""
import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
from dotenv import dotenv_values

from vetone_api import VetOneClient

PROJECT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_DIR / "data" / "raw"
DATABASE = PROJECT_DIR / "data" / "nordvet.duckdb"
EXPORT_DIR = PROJECT_DIR / "data" / "export"
SQL_DIR = Path(__file__).resolve().parent / "sql"
LOCAL_TIME = ZoneInfo("Europe/Copenhagen")  # Denmark and Sweden share the same clock.
RELOAD_DAYS = 14  # All late updates seen so far landed within about 8 days.
REPORT_TABLES = ["report_run", "report_clinic_summary", "report_clinic_window",
                 "report_clinic_day", "report_clinic_service"]


def fetch(date_from, date_to):
    """Download clinics and the window's appointments; save every page unchanged."""
    as_of = datetime.now(timezone.utc)
    credentials = dotenv_values(PROJECT_DIR / ".env")
    client = VetOneClient(credentials["VETONE_CLIENT_ID"], credentials["VETONE_CLIENT_SECRET"])
    run_dir = RAW_DIR / f"run_{as_of:%Y%m%dT%H%M%SZ}"
    run_dir.mkdir(parents=True)  # Only after a successful log-in: no empty folders.

    (run_dir / "clinics.json").write_text(client.get("/v1/clinics").text, encoding="utf-8")
    pages = 0
    for pages, text in enumerate(client.appointment_pages(date_from, date_to), start=1):
        (run_dir / f"appointments_page_{pages:04d}.json").write_text(text, encoding="utf-8")
        if pages % 50 == 0:
            print(f"  {pages} pages")

    # Written last: a folder with run.json is a complete download.
    run_info = {"as_of": as_of.isoformat(), "date_from": date_from, "date_to": date_to, "pages": pages}
    (run_dir / "run.json").write_text(json.dumps(run_info, indent=2), encoding="utf-8")
    print(f"fetch: {pages} pages saved to {run_dir.relative_to(PROJECT_DIR)}")
    return run_dir


def read_run(run_dir):
    """Read a saved run folder into a run row, a clinics table and an appointments table."""
    run_info = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    as_of = datetime.fromisoformat(run_info["as_of"])
    run = pd.DataFrame([{
        "run_id": run_dir.name,
        "as_of_utc": as_of.astimezone(timezone.utc).replace(tzinfo=None),
        "run_date": as_of.astimezone(LOCAL_TIME).date().isoformat(),  # "Today" for the report.
        "date_from": run_info["date_from"],
        "date_to": run_info["date_to"],
    }])

    clinics = pd.DataFrame(json.loads((run_dir / "clinics.json").read_text(encoding="utf-8"))["data"])

    records = []
    for file in sorted(run_dir.glob("appointments_page_*.json")):
        records.extend(json.loads(file.read_text(encoding="utf-8"))["data"])
    appointments = pd.DataFrame(records)
    for column in ["cancelled_at"]:  # Optional fields: make sure the column exists.
        if column not in appointments:
            appointments[column] = None

    # The API is live, so a record can move between pages while we page through
    # and show up twice. Keep the most recently updated version of each id.
    before = len(appointments)
    appointments = appointments.sort_values("updated_at").drop_duplicates("id", keep="last")
    if len(appointments) < before:
        print(f"  {before - len(appointments)} duplicate records dropped")

    def utc(column):
        """Timestamps as UTC without time zone, so they compare correctly in any SQL engine."""
        return pd.to_datetime(appointments[column], utc=True).dt.tz_localize(None)

    appointments = pd.DataFrame({
        "id": appointments["id"],
        "clinic_id": appointments["clinic_id"],
        "vet_id": appointments["vet_id"],
        "patient_ref": appointments["patient_ref"],
        "service": appointments["service"],
        # scheduled_at is written in the clinic's local time, so its first 10
        # characters are the local appointment date.
        "scheduled_date": appointments["scheduled_at"].str[:10],
        "scheduled_at_utc": utc("scheduled_at"),
        "duration_minutes": appointments["duration_minutes"],
        "status": appointments["status"],
        "created_at_utc": utc("created_at"),
        "updated_at_utc": utc("updated_at"),
        "cancelled_at_utc": utc("cancelled_at"),
        "run_id": run_dir.name,
    })
    return run, clinics, appointments


def load(con, run_dir):
    """Replace the window's appointments with this run's data, in one transaction."""
    run, clinics, appointments = read_run(run_dir)
    con.execute((SQL_DIR / "01_tables.sql").read_text(encoding="utf-8"))
    for name, frame in [("run_new", run), ("clinics_new", clinics), ("appointments_new", appointments)]:
        con.register(name, frame)  # Lets SQL read the pandas table by this name.

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute("DELETE FROM runs WHERE run_id IN (SELECT run_id FROM run_new)")
        con.execute("""
            INSERT INTO runs
            SELECT run_id, as_of_utc, CAST(run_date AS DATE), CAST(date_from AS DATE), CAST(date_to AS DATE)
            FROM run_new""")
        con.execute("DELETE FROM clinics")
        con.execute("""
            INSERT INTO clinics
            SELECT id, name, city, country, timezone, active, CAST(opened_on AS DATE) FROM clinics_new""")
        # Remove everything scheduled in the window (this also drops appointments
        # VetOne has deleted since the last run), and any id we are about to insert.
        con.execute("""
            DELETE FROM appointments
            WHERE scheduled_date BETWEEN (SELECT date_from FROM runs WHERE run_id = ?)
                                     AND (SELECT date_to FROM runs WHERE run_id = ?)
               OR id IN (SELECT id FROM appointments_new)""", [run_dir.name, run_dir.name])
        con.execute("""
            INSERT INTO appointments
            SELECT id, clinic_id, vet_id, patient_ref, service, CAST(scheduled_date AS DATE),
                   scheduled_at_utc, duration_minutes, status,
                   created_at_utc, updated_at_utc, cancelled_at_utc, run_id
            FROM appointments_new""")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")  # Leave the database exactly as before.
        raise
    total = con.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    print(f"load: {len(appointments)} appointments from {run.at[0, 'date_from']} to "
          f"{run.at[0, 'date_to']}; {total} in the database")


def build_views(con):
    """Run the SQL files in order: rules first, then the report tables."""
    for file in sorted(SQL_DIR.glob("*.sql")):
        if file.name != "01_tables.sql":
            con.execute(file.read_text(encoding="utf-8"))
    print("sql: views built")


def check(con):
    """Stop before the export if the data looks wrong."""
    checks = {
        "appointments with a status we don't know":
            "SELECT COUNT(*) FROM appointment_status WHERE inferred_status = 'unknown'",
        "appointments at a clinic missing from the clinic list":
            "SELECT COUNT(*) FROM appointments WHERE clinic_id NOT IN (SELECT clinic_id FROM clinics)",
        "appointments without a scheduled time":
            "SELECT COUNT(*) FROM appointments WHERE scheduled_at_utc IS NULL",
        "active clinics without appointments in the last 28 days":
            "SELECT COUNT(*) FROM report_clinic_summary WHERE slots_28_days IS NULL",
    }
    problems = []
    for description, query in checks.items():
        count = con.execute(query).fetchone()[0]
        if count:
            problems.append(f"{count} {description}")
    if problems:
        raise RuntimeError("check failed: " + "; ".join(problems))
    print("check: all passed")


def export(con):
    """Write each report table to a Parquet file for Power BI."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    for table in REPORT_TABLES:
        out_file = EXPORT_DIR / f"{table}.parquet"
        con.execute(f"COPY (SELECT * FROM {table}) TO '{out_file.as_posix()}' (FORMAT parquet)")
    print(f"export: {len(REPORT_TABLES)} tables written to {EXPORT_DIR.relative_to(PROJECT_DIR)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="date_from", help="first scheduled date to load (YYYY-MM-DD)")
    parser.add_argument("--reload", type=Path, help="load a saved run folder instead of calling the API")
    args = parser.parse_args()

    if args.reload:
        run_dir = args.reload.resolve()
    else:
        today = datetime.now(LOCAL_TIME).date()
        date_from = args.date_from or str(today - timedelta(days=RELOAD_DAYS))
        date.fromisoformat(date_from)  # Fails early on a malformed date.
        print(f"fetch: appointments scheduled {date_from} to {today}")
        run_dir = fetch(date_from, str(today))

    con = duckdb.connect(str(DATABASE))
    try:
        load(con, run_dir)
        build_views(con)
        check(con)
        export(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
