"""Exploration: do some patients (pets, via patient_ref) miss appointments again and again?

Uses inferred_status from inferred_status.py. Three questions:
  1. How many appointments does a patient have, and do patients visit several clinics?
  2. How many patients have 2 or more no-shows (or late cancellations), and how
     many would we expect by chance if every appointment had the same no-show rate?
  3. Is a patient more likely to miss an appointment after already missing one?

Run from the project folder, passing a download folder:
    .venv\\Scripts\\python.exe explore\\no_show_by_patient.py data\\raw\\last_21_days_20261107T105532Z
"""
import sys
from pathlib import Path

import pandas as pd

from inferred_status import download_time, infer_status, load_appointments

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)


def expected_with_two_or_more(n_per_patient, rate):
    """How many patients would have 2+ events by chance alone.

    If each appointment independently has the same probability `rate`, a patient
    with n appointments has 0 events with probability (1-rate)^n and exactly 1
    with probability n * rate * (1-rate)^(n-1). Everything else is 2 or more.
    Summing that over all patients gives the expected number of such patients.
    """
    n = n_per_patient
    p_zero = (1 - rate) ** n
    p_one = n * rate * (1 - rate) ** (n - 1)
    return (1 - p_zero - p_one).sum()


def repeat_analysis(appointments, status, eligible_statuses):
    """Observed vs chance number of patients with 2+ appointments of `status`."""
    eligible = appointments[appointments["inferred_status"].isin(eligible_statuses)]
    per_patient = eligible.groupby("patient_ref").agg(
        appointments=("id", "size"),
        events=("inferred_status", lambda s: (s == status).sum()),
    )
    rate = per_patient["events"].sum() / per_patient["appointments"].sum()
    observed = (per_patient["events"] >= 2).sum()
    by_chance = expected_with_two_or_more(per_patient["appointments"], rate)
    from_repeaters = per_patient.loc[per_patient["events"] >= 2, "events"].sum()

    print(f"\n=== {status}: rate {100 * rate:.1f}% over {len(eligible)} appointments "
          f"({', '.join(eligible_statuses)})")
    print("Patients by number of", status, "appointments:")
    print(per_patient["events"].value_counts().sort_index().to_string())
    print(f"Patients with 2 or more: {observed} observed, {by_chance:.1f} expected by chance")
    print(f"They account for {from_repeaters} of {per_patient['events'].sum()} {status} appointments "
          f"({100 * from_repeaters / per_patient['events'].sum():.1f}%)")
    return per_patient


def after_previous(appointments):
    """No-show rate of an appointment, split by what happened at the patient's previous one."""
    expected = appointments[appointments["inferred_status"].isin(["completed", "no_show"])]
    expected = expected.sort_values(["patient_ref", "scheduled"])
    # shift(1) within each patient: the status of that patient's previous appointment.
    expected = expected.assign(previous=expected.groupby("patient_ref")["inferred_status"].shift(1))
    later = expected.dropna(subset=["previous"])
    table = later.groupby("previous").agg(
        appointments=("id", "size"),
        no_show=("inferred_status", lambda s: (s == "no_show").sum()),
    )
    table["rate_%"] = (100 * table["no_show"] / table["appointments"]).round(1)
    print("\n=== No-show rate of an appointment, by the outcome of the same patient's previous one")
    print(table)


def main():
    folder = Path(sys.argv[1])
    as_of = download_time(folder)
    appointments = load_appointments(folder)
    appointments["scheduled"] = pd.to_datetime(appointments["scheduled_at"], utc=True)
    appointments["cancelled"] = pd.to_datetime(appointments["cancelled_at"], utc=True)
    appointments["inferred_status"] = appointments.apply(infer_status, axis=1, as_of=as_of)

    per_patient = appointments.groupby("patient_ref").agg(
        appointments=("id", "size"), clinics=("clinic_id", "nunique"))
    print(f"{len(appointments)} appointments, {len(per_patient)} patients "
          f"(rules as of {as_of:%Y-%m-%d %H:%M} UTC)")
    print("\n=== Appointments per patient (all statuses)")
    print(per_patient["appointments"].value_counts().sort_index().to_string())
    print(f"Patients seen at more than one clinic: {(per_patient['clinics'] > 1).sum()}")

    no_shows = repeat_analysis(appointments, "no_show", ["completed", "no_show"])
    repeat_analysis(appointments, "late_cancelled", ["completed", "no_show", "late_cancelled", "cancelled"])
    after_previous(appointments)

    print("\n=== Patients with the most no-shows")
    worst = no_shows.sort_values("events", ascending=False).head(10)
    clinic = appointments.groupby("patient_ref")["clinic_id"].agg(lambda c: ", ".join(sorted(set(c))))
    print(worst.assign(clinic=clinic).rename(columns={"events": "no_show"}))


if __name__ == "__main__":
    main()
