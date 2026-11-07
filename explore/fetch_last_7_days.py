"""Exploration: download the last 7 days of appointments, exactly as the API returns them.

Run from the project folder:
    .venv\\Scripts\\python.exe explore\\fetch_last_7_days.py

Each API page is saved unchanged as a JSON file under data/raw/ (ignored by Git),
so we can look at the real responses before designing the pipeline.
Credentials are read from .env and never printed.
"""
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values

BASE_URL = "https://vetone-api.kinddesert-e2c4fbdc.westeurope.azurecontainerapps.io"
PAGE_SIZE = 100  # The docs give no maximum, so we stay modest on a production system.
MAX_PAGES = 1000  # Safety stop in case the cursor never ends.
PROJECT_DIR = Path(__file__).resolve().parent.parent


def log_in(session, credentials):
    """Exchange client ID and secret for an access token and attach it to the session."""
    response = session.post(
        f"{BASE_URL}/auth/token",
        json={
            "client_id": credentials["VETONE_CLIENT_ID"],
            "client_secret": credentials["VETONE_CLIENT_SECRET"],
        },
        timeout=90,  # The API can take ~20 seconds to wake up.
    )
    response.raise_for_status()
    session.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


def get(session, credentials, path, params=None):
    """GET with a re-login when the token has expired and a pause when rate limited."""
    for attempt in range(5):
        response = session.get(f"{BASE_URL}{path}", params=params, timeout=90)
        if response.status_code == 401:
            print("  token rejected, logging in again")
            log_in(session, credentials)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            wait = int(response.headers.get("Retry-After", 2 ** attempt))
            print(f"  HTTP {response.status_code}, waiting {wait}s before retrying")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response
    raise RuntimeError(f"Gave up on {path} after 5 attempts")


def main():
    credentials = dotenv_values(PROJECT_DIR / ".env")
    run_time = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = PROJECT_DIR / "data" / "raw" / f"last_7_days_{run_time}"
    out_dir.mkdir(parents=True)

    session = requests.Session()
    log_in(session, credentials)

    # Clinics: small reference list, saved once.
    response = get(session, credentials, "/v1/clinics")
    (out_dir / "clinics.json").write_text(response.text, encoding="utf-8")
    print(f"clinics: {len(response.json()['data'])}")

    # Appointments: no date filter, so the API's default of "last 7 days" applies.
    appointments = []
    cursor = None
    for page in range(1, MAX_PAGES + 1):
        params = {"limit": PAGE_SIZE}
        if cursor:
            params["cursor"] = cursor
        response = get(session, credentials, "/v1/appointments", params)
        (out_dir / f"appointments_page_{page:04d}.json").write_text(response.text, encoding="utf-8")

        body = response.json()
        appointments.extend(body["data"])
        cursor = body.get("next_cursor")
        if not cursor:
            break
    else:
        print(f"WARNING: stopped after {MAX_PAGES} pages, the data may be incomplete")

    # A first summary of what came back.
    ids = [a["id"] for a in appointments]
    dates = sorted(a["scheduled_at"][:10] for a in appointments)
    fields = Counter(field for a in appointments for field in a)
    print(f"pages: {page}, appointments: {len(appointments)}, unique ids: {len(set(ids))}")
    print(f"scheduled dates: {dates[0]} to {dates[-1]}" if dates else "no appointments")
    print("per day:", dict(sorted(Counter(dates).items())))
    print("status:", dict(Counter(a.get("status") for a in appointments).most_common()))
    print("service:", dict(Counter(a.get("service") for a in appointments).most_common()))
    print("fields (how many records have each):", dict(fields.most_common()))
    print(f"saved to: {out_dir.relative_to(PROJECT_DIR)}")


if __name__ == "__main__":
    main()
