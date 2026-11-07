"""Exploration: appointments of each status and the no-show rate per clinic,
per vet and per service.

Shows two counts side by side: VetOne's own status, and inferred_status from
the rules in inferred_status.py. Where they differ, the rules have changed
the picture (mostly recent no-shows that VetOne hasn't recorded yet).
The no-show rate is no_show / (completed + no_show) on inferred_status.
For each grouping, a bar chart of the rate is saved in data/plots/.

Run from the project folder, passing a download folder:
    .venv\\Scripts\\python.exe explore\\status_by_group.py data\\raw\\last_21_days_20261107T105532Z
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Draw straight to a file, without opening a window.
import matplotlib.pyplot as plt
import pandas as pd

# Reuse the loading and the rules, so there is only one version of each.
from inferred_status import download_time, infer_status, load_appointments

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", None)
pd.set_option("display.max_rows", None)  # Print every clinic and every vet.

PROJECT_DIR = Path(__file__).resolve().parent.parent
VETONE_ORDER = ["completed", "no_show", "cancelled", "booked"]
INFERRED_ORDER = ["completed", "no_show", "late_cancelled", "cancelled", "pending"]


def no_show_rate(no_show, completed):
    """Of the clients who were expected and whose outcome is known, the share
    (in %) who didn't come. Pending and cancellations are left out."""
    return 100 * no_show / (completed + no_show)


def status_counts(appointments, group_by):
    """One row per group, with counts for both status columns side by side."""
    # crosstab counts how often each combination of group and status occurs.
    # reindex puts the status columns in a fixed order (missing ones become 0).
    vetone = pd.crosstab(appointments[group_by], appointments["status"])
    vetone = vetone.reindex(columns=VETONE_ORDER, fill_value=0)
    inferred = pd.crosstab(appointments[group_by], appointments["inferred_status"])
    inferred = inferred.reindex(columns=INFERRED_ORDER, fill_value=0)

    # Two-level column names, e.g. ("vetone", "no_show") and ("inferred", "no_show"),
    # so the two sets of counts stay apart when printed next to each other.
    table = pd.concat({"vetone": vetone, "inferred": inferred}, axis=1)
    table.insert(0, ("", "total"), vetone.sum(axis=1))
    rate = no_show_rate(inferred["no_show"], inferred["completed"])
    table[("inferred", "no_show_rate_%")] = rate.round(1)
    return table.sort_values(("inferred", "no_show_rate_%"), ascending=False)


def plot_rates(table, label, overall_rate, source_name):
    """Horizontal bar chart of the no-show rate, highest at the top."""
    rates = table[("inferred", "no_show_rate_%")].sort_values()  # barh draws bottom-up.
    height = max(3, 0.22 * len(rates) + 1.5)  # Room for one readable bar per group.
    fig, ax = plt.subplots(figsize=(9, height))
    ax.barh(rates.index, rates.values, color="#4C72B0")
    ax.axvline(overall_rate, color="grey", linestyle="--", linewidth=1,
               label=f"All appointments: {overall_rate:.1f}%")
    ax.set_xlabel("No-show rate in %  =  no_show / (completed + no_show)")
    ax.set_title(f"No-show rate per {label} ({source_name})")
    ax.margins(y=0.01)
    ax.grid(True, axis="x", alpha=0.3)
    ax.legend(loc="lower right")

    out_file = PROJECT_DIR / "data" / "plots" / f"no_show_rate_by_{label}_{source_name}.png"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_file, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"Plot saved to {out_file.relative_to(PROJECT_DIR)}")


def main():
    folder = Path(sys.argv[1])
    as_of = download_time(folder)
    appointments = load_appointments(folder)
    appointments["scheduled"] = pd.to_datetime(appointments["scheduled_at"], utc=True)
    appointments["cancelled"] = pd.to_datetime(appointments["cancelled_at"], utc=True)
    appointments["inferred_status"] = appointments.apply(infer_status, axis=1, as_of=as_of)

    # Clinic names, so the table is readable. A left merge keeps every appointment
    # even if its clinic were missing from clinics.json.
    clinics = pd.DataFrame(json.loads((folder / "clinics.json").read_text(encoding="utf-8"))["data"])
    clinics = clinics.rename(columns={"id": "clinic_id", "name": "clinic_name"})
    appointments = appointments.merge(clinics[["clinic_id", "clinic_name", "country"]], on="clinic_id", how="left")
    appointments["clinic"] = appointments["clinic_id"] + " " + appointments["clinic_name"].str.replace("Nordvet ", "")

    dates = appointments["scheduled_at"].str[:10]
    print(f"{len(appointments)} appointments from {dates.min()} to {dates.max()}, "
          f"rules evaluated as of {as_of:%Y-%m-%d %H:%M} UTC")
    counts = appointments["inferred_status"].value_counts()
    overall_rate = no_show_rate(counts.get("no_show", 0), counts.get("completed", 0))
    print(f"No-show rate over all appointments: {overall_rate:.1f}%")

    clinic_table = status_counts(appointments, "clinic")
    print(f"\n=== Per clinic ({len(clinic_table)} clinics with appointments), sorted by no-show rate")
    print(clinic_table)

    # Vets: also show which clinic(s) each vet works at.
    vet_table = status_counts(appointments, "vet_id")
    vet_clinics = appointments.groupby("vet_id")["clinic_id"].agg(lambda ids: ", ".join(sorted(set(ids))))
    vet_table.insert(0, ("", "clinic_id"), vet_clinics)
    print(f"\n=== Per vet ({len(vet_table)} vets), sorted by no-show rate")
    print(vet_table)

    service_table = status_counts(appointments, "service")
    print(f"\n=== Per service ({len(service_table)} services), sorted by no-show rate")
    print(service_table)

    vets_per_clinic = appointments.groupby("clinic_id")["vet_id"].nunique()
    clinics_per_vet = appointments.groupby("vet_id")["clinic_id"].nunique()
    print(f"\nVets per clinic: {vets_per_clinic.min()} to {vets_per_clinic.max()}; "
          f"vets working at more than one clinic: {(clinics_per_vet > 1).sum()}")

    inactive = clinics.loc[~clinics["active"], "clinic_id"].tolist()
    without = sorted(set(clinics["clinic_id"]) - set(appointments["clinic_id"]))
    print(f"Inactive clinics: {inactive}; clinics without appointments: {without}\n")

    # Vets are labelled with their clinic, so the chart shows where they work.
    vet_table.index = vet_table.index + " (" + vet_table[("", "clinic_id")] + ")"
    for table, label in [(clinic_table, "clinic"), (vet_table, "vet"), (service_table, "service")]:
        plot_rates(table, label, overall_rate, folder.name)


if __name__ == "__main__":
    main()
