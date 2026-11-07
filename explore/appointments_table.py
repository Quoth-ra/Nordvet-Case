"""Exploration: combine all downloaded appointment pages into one table,
then look at how long after the scheduled time completed appointments are updated.

Run from the project folder, passing a download folder:
    .venv\\Scripts\\python.exe explore\\appointments_table.py data\\raw\\last_7_days_20261107T094443Z
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Draw straight to a file, without opening a window.
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent

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

    # Sort from shortest to longest time difference. reset_index(drop=True)
    # renumbers the rows 0, 1, 2, ... in the new order, so the row number
    # becomes each appointment's position in the sorted list.
    result = result.sort_values("time_difference_minutes").reset_index(drop=True)
    print(f"\n=== Completed appointments, sorted by time difference: {len(result)} rows")
    print(result)

    print("\n=== Summary of the two minute columns")
    print(result[["time_difference_minutes", "duration_minutes"]].describe())

    plot_sorted_differences(result, Path(folder).name)


def plot_sorted_differences(result, source_name):
    """Plot each completed appointment's time difference, in sorted order.

    Top panel: the full range. Bottom panel: the same line zoomed in to 0-400 minutes,
    because a few extreme cases flatten everything else in the top panel.
    """
    zoom_max = 400
    cases = result.index + 1  # Count cases from 1 instead of 0.
    minutes = result["time_difference_minutes"]
    cut_off = (minutes > zoom_max).sum()

    fig, (full, zoom) = plt.subplots(2, 1, figsize=(10, 9), sharex=True)
    full.plot(cases, minutes)
    full.set_title(f"Minutes from scheduled time to status update ({source_name})")

    zoom.plot(cases, minutes)
    zoom.set_ylim(0, zoom_max)
    zoom.set_title(f"Zoomed to 0-{zoom_max} minutes ({cut_off} cases above {zoom_max} not shown)")
    zoom.set_xlabel("Case (completed appointments, sorted)")

    for ax in (full, zoom):
        ax.set_ylabel("time_difference_minutes")
        ax.grid(True, alpha=0.3)

    out_file = PROJECT_DIR / "data" / "plots" / f"completed_time_difference_{source_name}.png"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=120, bbox_inches="tight")
    print(f"\nPlot saved to {out_file.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
