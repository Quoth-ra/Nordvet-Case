"""Check the SQL rules against the pandas rules used during exploration.

Both are applied to the same saved run; every appointment must get the same
inferred_status. Run it after run_pipeline.py, from the project folder:
    .venv\\Scripts\\python.exe pipeline\\check_against_pandas.py data\\raw\\run_20261107T120000Z
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR / "explore"))
from inferred_status import infer_status, load_appointments  # noqa: E402  (the exploration code)


def main():
    run_dir = Path(sys.argv[1]).resolve()
    as_of = datetime.fromisoformat(json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["as_of"])

    python = load_appointments(run_dir).drop_duplicates("id")
    python["scheduled"] = pd.to_datetime(python["scheduled_at"], utc=True)
    python["cancelled"] = pd.to_datetime(python["cancelled_at"], utc=True)
    python["python_status"] = python.apply(infer_status, axis=1, as_of=as_of)

    con = duckdb.connect(str(PROJECT_DIR / "data" / "nordvet.duckdb"), read_only=True)
    sql = con.execute("SELECT id, inferred_status AS sql_status FROM appointment_status WHERE run_id = ?",
                      [run_dir.name]).df()
    con.close()

    both = python[["id", "status", "python_status"]].merge(sql, on="id", how="outer", indicator=True)
    missing = (both["_merge"] != "both").sum()
    different = both[(both["_merge"] == "both") & (both["python_status"] != both["sql_status"])]
    print(f"{len(python)} appointments in the run, {len(sql)} in the database from this run")
    print(pd.crosstab(both["python_status"], both["sql_status"], margins=True))
    if missing or len(different):
        print(f"MISMATCH: {missing} only on one side, {len(different)} with a different status")
        print(different.head(20))
        sys.exit(1)
    print("OK: SQL and pandas agree on every appointment")


if __name__ == "__main__":
    main()
