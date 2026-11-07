"""Exploration: combine all downloaded appointment pages into one table,
then look at how long after the scheduled time completed appointments are updated.

Run from the project folder, passing a download folder:
    .venv\\Scripts\\python.exe explore\\appointments_table.py data\\raw\\last_7_days_20261107T094443Z
"""
import json
import sys
from pathlib import Path

import pandas as pd

# Show all columns side by side instead of hiding some behind "...".
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)


def load_appointments(folder):
    """Read every appointments_page_*.json file and stack the records into one table."""
    records = []
    files = sorted(Path(folder).glob("appointments_page_*.json"))
    for file in files:
        page = json.loads(file.read_text(encoding="utf-8"))
        records.extend(page["data"])  # Each page holds its appointments under "data".
    print(f"Read {len(records)} appointments from {len(files)} files in {folder}")
    # One row per appointment, one column per field. Fields missing from a record
    # (like cancelled_at on non-cancelled appointments) become empty (NaN).
    return pd.DataFrame(records)


def main():
    folder = sys.argv[1]
    appointments = load_appointments(folder)

    print("\n=== All appointments (pandas shows the first and last rows)")
    print(appointments)

    # Keep only completed appointments. .copy() makes a separate table,
    # so adding a column below doesn't touch the full table.
    completed = appointments[appointments["status"] == "completed"].copy()

    # The two timestamps use different time zones: scheduled_at is local time
    # (+01:00) and updated_at is UTC (Z). utc=True converts both to UTC,
    # so subtracting them gives the real time between them.
    scheduled = pd.to_datetime(completed["scheduled_at"], utc=True)
    updated = pd.to_datetime(completed["updated_at"], utc=True)
    completed["time_difference_minutes"] = (updated - scheduled).dt.total_seconds() / 60

    result = completed[["id", "clinic_id", "vet_id", "time_difference_minutes", "duration_minutes"]]
    print(f"\n=== Completed appointments: {len(result)} rows")
    print(result)

    print("\n=== Summary of the two minute columns")
    print(result[["time_difference_minutes", "duration_minutes"]].describe())


if __name__ == "__main__":
    main()
