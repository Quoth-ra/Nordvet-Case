"""Exploration: apply the inferred_status rules to one download.

VetOne staff mark no-shows by hand the next working day, so the official status
lags behind. These rules use the timestamps to infer the status earlier:

    VetOne status  condition                                       inferred_status
    completed                                                      completed
    no_show                                                        no_show
    booked         more than 300 minutes after the start           no_show
    booked         less than that, or in the future                pending
    cancelled      cancelled after the start                       no_show
    cancelled      cancelled less than 24 hours before the start   late_cancelled
    cancelled      cancelled earlier                               cancelled

The rules are evaluated at the time of the download (from the folder name),
so the result always matches the data it was computed from.

Run from the project folder:
    .venv\\Scripts\\python.exe explore\\inferred_status.py data\\raw\\last_7_days_20261107T094443Z
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

NOT_COMPLETED_AFTER_MINUTES = 300  # 99% of completed appointments are marked within 260.
LATE_CANCELLATION_MINUTES = 24 * 60  # Cancelled less than 24 hours before the start.


def load_appointments(folder):
    """Read every appointments_page_*.json file into one table."""
    records = []
    for file in sorted(Path(folder).glob("appointments_page_*.json")):
        records.extend(json.loads(file.read_text(encoding="utf-8"))["data"])
    return pd.DataFrame(records)


def download_time(folder):
    """Read the download time from a folder name like last_7_days_20261107T094443Z."""
    stamp = Path(folder).name.rsplit("_", 1)[-1]
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def infer_status(row, as_of):
    """Apply the rules to one appointment. Returns the inferred status."""
    status = row["status"]
    start = row["scheduled"]

    if status in ("completed", "no_show"):
        return status  # VetOne's final status, nothing to infer.

    if status == "booked":
        minutes_since_start = (as_of - start).total_seconds() / 60
        if minutes_since_start > NOT_COMPLETED_AFTER_MINUTES:
            return "no_show"  # Would have been marked completed by now.
        return "pending"  # Too early to tell, or still in the future.

    if status == "cancelled":
        minutes_before_start = (start - row["cancelled"]).total_seconds() / 60
        if minutes_before_start < 0:
            return "no_show"  # Cancelled after it had started.
        if minutes_before_start < LATE_CANCELLATION_MINUTES:
            return "late_cancelled"
        return "cancelled"

    return "unknown"  # A status we haven't seen before: flag it rather than guess.


def main():
    folder = sys.argv[1]
    as_of = download_time(folder)
    appointments = load_appointments(folder)
    print(f"{len(appointments)} appointments, rules evaluated as of {as_of:%Y-%m-%d %H:%M} UTC")

    # Timestamps as real times in UTC, so they can be compared and subtracted.
    appointments["scheduled"] = pd.to_datetime(appointments["scheduled_at"], utc=True)
    appointments["cancelled"] = pd.to_datetime(appointments["cancelled_at"], utc=True)

    # Run infer_status on every row (axis=1 means "per row").
    appointments["inferred_status"] = appointments.apply(infer_status, axis=1, as_of=as_of)
    appointments["is_inferred"] = appointments["inferred_status"] != appointments["status"]

    # The appointment's local date: the first 10 characters of scheduled_at,
    # which is written in the clinic's local time.
    appointments["date"] = appointments["scheduled_at"].str[:10]

    print("\n=== VetOne status (rows) against inferred_status (columns)")
    print(pd.crosstab(appointments["status"], appointments["inferred_status"], margins=True))

    print("\n=== inferred_status per day")
    print(pd.crosstab(appointments["date"], appointments["inferred_status"], margins=True))

    print("\n=== no-shows per day: confirmed by VetOne vs. inferred by the rules")
    no_shows = appointments[appointments["inferred_status"] == "no_show"]
    print(pd.crosstab(no_shows["date"], no_shows["is_inferred"].map({False: "confirmed", True: "inferred"}), margins=True))


if __name__ == "__main__":
    main()
