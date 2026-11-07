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

    # The two timestamps use different time zones: scheduled_at is local time
    # (+01:00) and updated_at is UTC (Z). utc=True converts both to UTC,
    # so subtracting them gives the real time between them.
    # Negative values mean the last update happened before the scheduled time.
    scheduled = pd.to_datetime(appointments["scheduled_at"], utc=True)
    updated = pd.to_datetime(appointments["updated_at"], utc=True)
    appointments["time_difference_minutes"] = (updated - scheduled).dt.total_seconds() / 60

    # Completed keeps the fixed 0-400 zoom. The other statuses can be negative,
    # so their zoom is chosen from the data (see plot_sorted_differences).
    zoom_ranges = {"completed": (0, 400)}
    for status in ["completed", "no_show", "cancelled", "booked"]:
        analyse_status(appointments, status, Path(folder).name, zoom_ranges.get(status))


def analyse_status(appointments, status, source_name, zoom_range):
    """Print the sorted time differences for one status and save its chart."""
    # Keep only this status. .copy() makes a separate table.
    subset = appointments[appointments["status"] == status].copy()
    result = subset[["id", "clinic_id", "vet_id", "time_difference_minutes", "duration_minutes"]]

    # Sort from shortest to longest time difference. reset_index(drop=True)
    # renumbers the rows 0, 1, 2, ... in the new order, so the row number
    # becomes each appointment's position in the sorted list.
    result = result.sort_values("time_difference_minutes").reset_index(drop=True)
    print(f"\n=== {status}: {len(result)} rows, sorted by time difference")
    print(result)

    print(f"\n=== {status}: summary of the two minute columns")
    print(result[["time_difference_minutes", "duration_minutes"]].describe())

    plot_sorted_differences(result, status, source_name, zoom_range)


def plot_sorted_differences(result, status, source_name, zoom_range=None):
    """Plot each appointment's time difference, in sorted order.

    Top panel: the full range. Bottom panel: the same line zoomed in, because a few
    extreme cases can flatten everything else in the top panel. Without a given
    zoom_range, the zoom shows the middle 98% of cases (1st to 99th percentile).
    """
    cases = result.index + 1  # Count cases from 1 instead of 0.
    minutes = result["time_difference_minutes"]

    if zoom_range is None:
        low, high = minutes.quantile(0.01), minutes.quantile(0.99)
        padding = (high - low) * 0.05  # A little space above and below the line.
        zoom_range = (low - padding, high + padding)
        zoom_label = "middle 98% of cases"
    else:
        zoom_label = f"{zoom_range[0]:.0f} to {zoom_range[1]:.0f} minutes"
    outside = ((minutes < zoom_range[0]) | (minutes > zoom_range[1])).sum()

    fig, (full, zoom) = plt.subplots(2, 1, figsize=(10, 9), sharex=True)
    full.plot(cases, minutes)
    full.set_title(f"{status}: minutes from scheduled time to last update ({source_name})")

    zoom.plot(cases, minutes)
    zoom.set_ylim(*zoom_range)
    zoom.set_title(f"Zoomed to {zoom_label} ({outside} cases outside not shown)")
    zoom.set_xlabel(f"Case ({status} appointments, sorted)")

    for ax in (full, zoom):
        ax.set_ylabel("time_difference_minutes")
        ax.grid(True, alpha=0.3)
        ax.axhline(0, color="grey", linewidth=0.8)  # 0 = the scheduled time.

    out_file = PROJECT_DIR / "data" / "plots" / f"{status}_time_difference_{source_name}.png"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=120, bbox_inches="tight")
    plt.close(fig)  # Free the memory before drawing the next status.
    print(f"\nPlot saved to {out_file.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
