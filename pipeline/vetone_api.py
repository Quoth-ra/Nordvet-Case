"""Small client for the VetOne API: log-in, retries and paging.

Behaviour found while exploring that the docs don't mention:
  - HTTP 429 (rate limit) after about 50-90 pages in a row, with Retry-After ~60 s
  - occasional HTTP 500 that succeeds on retry
  - the token response has no expiry time, so we log in again on any 401
  - the API scales down when idle, so the first call can take ~20 s
"""
import time

import requests

BASE_URL = "https://vetone-api.kinddesert-e2c4fbdc.westeurope.azurecontainerapps.io"
PAGE_SIZE = 100  # The docs give no maximum; we stay modest on a production system.
MAX_PAGES = 5000  # Safety stop in case the cursor never ends (a backfill is ~600 pages).
ATTEMPTS = 6


class VetOneClient:
    def __init__(self, client_id, client_secret):
        self._credentials = {"client_id": client_id, "client_secret": client_secret}
        self._session = requests.Session()
        self._log_in()

    def _request(self, method, path, **kwargs):
        """Send a request; on 429 or 5xx, wait as long as the API asks and try again."""
        for attempt in range(ATTEMPTS):
            response = self._session.request(method, f"{BASE_URL}{path}", timeout=90, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                wait = int(response.headers.get("Retry-After", 2 ** attempt))
                print(f"  HTTP {response.status_code}, waiting {wait}s before retrying")
                time.sleep(wait)
                continue
            return response
        raise RuntimeError(f"Gave up on {path} after {ATTEMPTS} attempts")

    def _log_in(self):
        """Exchange client ID and secret for an access token."""
        response = self._request("POST", "/auth/token", json=self._credentials)
        response.raise_for_status()
        self._session.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

    def get(self, path, params=None):
        """GET with a re-login if the token was rejected. Returns the response."""
        for _ in range(ATTEMPTS):
            response = self._request("GET", path, params=params)
            if response.status_code == 401:
                print("  token rejected, logging in again")
                self._log_in()
                continue
            response.raise_for_status()
            return response
        raise RuntimeError(f"Gave up on {path} after {ATTEMPTS} attempts")

    def appointment_pages(self, date_from, date_to):
        """Yield the raw text of each appointments page for scheduled dates
        date_from to date_to (both included, YYYY-MM-DD), following the cursor."""
        cursor = None
        for _ in range(MAX_PAGES):
            params = {"from": date_from, "to": date_to, "limit": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor
            response = self.get("/v1/appointments", params)
            yield response.text
            cursor = response.json().get("next_cursor")
            if not cursor:
                return
        raise RuntimeError(f"Stopped after {MAX_PAGES} pages; the cursor never ended")
