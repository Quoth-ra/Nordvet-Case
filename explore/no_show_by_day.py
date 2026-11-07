"""Exploration: are there days with a high no-show rate at several clinics at once?

Same rate as in status_by_group.py: no_show / (completed + no_show) on inferred_status.
Prints the rate per day over all clinics and saves two charts in data/plots/:
  - the rate per day over all clinics, with the number of expected appointments
  - a heatmap: one row per clinic, one column per day, colour = no-show rate

Run from the project folder, passing a download folder:
    .venv\\Scripts\\python.exe explore\\no_show_by_day.py data\\raw\\last_21_days_20261107T105532Z
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Draw straight to a file, without opening a window.
import matplotlib.pyplot as plt
import pandas as pd

from inferred_status import download_time, infer_status, load_appointments

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)

PROJECT_DIR = Path(__file__).resolve().parent.parent


def main():
    folder = Path(sys.argv[1])
    as_of = download_time(folder)
    appointments = load_appointments(folder)
    appointments["scheduled"] = pd.to_datetime(appointments["scheduled_at"], utc=True)
    appointments["cancelled"] = pd.to_datetime(appointments["cancelled_at"], utc=True)
    appointments["inferred_status"] = appointments.apply(infer_status, axis=1, as_of=as_of)
    appointments["date"] = appointments["scheduled_at"].str[:10]  # The clinic's local date.

    clinics = pd.DataFrame(json.loads((folder / "clinics.json").read_text(encoding="utf-8"))["data"])
    names = clinics.set_index("id")["name"].str.replace("Nordvet ", "")
    appointments["clinic"] = appointments["clinic_id"] + " " + appointments["clinic_id"].map(names)

    # Only appointments whose outcome is known and where the client was expected.
    expected = appointments[appointments["inferred_status"].isin(["completed", "no_show"])].copy()
    expected["is_no_show"] = expected["inferred_status"] == "no_show"  # True counts as 1.

    # Per day over all clinics: mean of True/False = share of no-shows.
    per_day = expected.groupby("date").agg(expected=("is_no_show", "size"), no_show=("is_no_show", "sum"))
    per_day["rate_%"] = (100 * per_day["no_show"] / per_day["expected"]).round(1)
    per_day.insert(0, "weekday", pd.to_datetime(per_day.index).strftime("%a"))
    print(f"=== No-show rate per day, all clinics (rules as of {as_of:%Y-%m-%d %H:%M} UTC; the last day is not over)")
    print(per_day)

    # Per clinic and day: rows = clinics, columns = days.
    rates = 100 * expected.pivot_table(index="clinic", columns="date", values="is_no_show", aggfunc="mean")
    counts = expected.pivot_table(index="clinic", columns="date", values="is_no_show", aggfunc="size")
    order = rates.mean(axis=1).sort_values(ascending=False).index  # Highest clinics at the top.
    rates, counts = rates.loc[order], counts.loc[order]
    print("\n=== Expected appointments per clinic and day: median", counts.stack().median(),
          ", min", counts.stack().min(), ", max", counts.stack().max())

    source = folder.name
    plot_per_day(per_day, source)
    plot_heatmap(rates, source)


def plot_per_day(per_day, source):
    """Rate per day over all clinics (bars) with the number of expected appointments (line)."""
    labels = [f"{d[5:]} {w}" for d, w in zip(per_day.index, per_day["weekday"])]
    fig, ax = plt.subplots(figsize=(12, 4.5))
    ax.bar(labels, per_day["rate_%"], color="#4C72B0")
    ax.set_ylabel("No-show rate in %")
    ax.set_title(f"No-show rate per day, all clinics ({source})")
    ax.tick_params(axis="x", rotation=60)
    ax.grid(True, axis="y", alpha=0.3)
    volume = ax.twinx()  # A second y-axis on the right for the volume.
    volume.plot(labels, per_day["expected"], color="#DD8452", marker="o", label="expected appointments")
    volume.set_ylabel("Expected appointments (completed + no_show)")
    volume.set_ylim(0, None)
    volume.legend(loc="upper left")
    save(fig, f"no_show_rate_by_day_{source}.png")


def plot_heatmap(rates, source):
    """One row per clinic, one column per day. Empty cells (no appointments) stay white."""
    fig, ax = plt.subplots(figsize=(14, 11))
    image = ax.imshow(rates.values, aspect="auto", cmap="Reds", vmin=0, vmax=50)
    days = pd.to_datetime(rates.columns)
    ax.set_xticks(range(len(days)), [d.strftime("%m-%d %a") for d in days], rotation=60)
    ax.set_yticks(range(len(rates.index)), rates.index)
    for row in range(rates.shape[0]):  # Write the rate in each cell, rounded.
        for col in range(rates.shape[1]):
            value = rates.iat[row, col]
            if pd.notna(value):
                ax.text(col, row, f"{value:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if value > 30 else "black")
    fig.colorbar(image, ax=ax, label="No-show rate in % (capped at 50)")
    ax.set_title(f"No-show rate per clinic and day ({source}); clinics sorted by average rate")
    save(fig, f"no_show_rate_by_clinic_and_day_{source}.png")


def save(fig, name):
    out_file = PROJECT_DIR / "data" / "plots" / name
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Plot saved to {out_file.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
