# Nordvet no-show view: a first slice

A daily pipeline that turns VetOne appointments into a no-show report per clinic, so Nordvet's Head of Operations can start each morning knowing how every clinic did yesterday and over the last weeks.

It runs on a laptop for the demo. Where it would run for Nordvet is described [below](#where-it-would-run-for-nordvet). What the data shows is in [FINDINGS.md](FINDINGS.md), and every choice, with its reason and the alternative considered, is in [DECISIONS.md](DECISIONS.md).

## What it does

VetOne staff record no-shows by hand, usually the next working day. At 06:00 most of yesterday's no-shows still have the status `booked`, so a report on VetOne's status alone would show almost none. The pipeline therefore derives an `inferred_status` from the timestamps:

| VetOne status | Condition | `inferred_status` |
|---|---|---|
| `completed`, `no_show` | | taken as is |
| `booked` | more than 300 minutes after the start | `no_show` |
| `booked` | less than that, or in the future | `pending` (left out of all rates) |
| `cancelled` | cancelled after the start | `no_show` |
| `cancelled` | less than 24 hours before the start | `late_cancelled` |
| `cancelled` | earlier | `cancelled` |

From these it reports, per clinic, for the last day with appointments, the last 7 days and the last 28 days:

- **No-show rate** = no-shows / (completed + no-shows): of the clients who were expected, how many didn't come.
- **Late-cancel rate** and **cancel rate** = late or early cancellations / all slots with a known outcome.
- **Lost vet hours** = booked minutes of no-shows and late cancellations, as a stand-in for lost money (the API has no prices).

The Power BI report has two pages: a list of the active clinics sorted by the 28-day no-show rate, and a drill-through page per clinic with its daily rate against the network, its rate per service, and how many of its no-shows are still inferred.

## How to run it

Requirements: Windows, Python 3.13, and [Power BI Desktop](https://www.microsoft.com/power-platform/products/power-bi/desktop) (free) for the report.

**Setup, once**, in the project folder:

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Then put the VetOne client ID and secret into `.env`. It is ignored by Git.

**First run: load everything the API has.** About 600 pages, which took 10 minutes on 7 November, including waits for the API's rate limit:

```bash
.venv\Scripts\python.exe pipeline\run_pipeline.py --from 2026-08-06
```

**Daily run: the last 14 days.** This takes about 2 minutes:

```bash
.venv\Scripts\python.exe pipeline\run_pipeline.py
```

**The report:** open `powerbi\NordvetNoShow.pbip` in Power BI Desktop and click **Refresh**. It reads the Parquet files the pipeline writes to `C:\Users\Public\Nordvet\export\` (the `ExportFolder` parameter in Power BI).

Two more commands:

```bash
.venv\Scripts\python.exe pipeline\run_pipeline.py --reload data\raw\run_<folder>
```

loads a saved download again without calling the API, for example after changing a rule.

```bash
.venv\Scripts\python.exe pipeline\check_against_pandas.py data\raw\run_<folder>
```

checks that the SQL rules give every appointment the same status as the pandas version written during exploration.

## How it works

```
VetOne API → fetch → raw JSON → load into DuckDB → SQL views → check → Parquet → Power BI
```

`pipeline/run_pipeline.py` runs five steps:

1. **fetch:** downloads the clinics and the window's appointments and saves every page unchanged in `data/raw/run_<UTC time>/`. A `run.json` written last marks a complete download.
2. **load:** replaces every appointment scheduled in the window with what the API returned, in one transaction. This also removes appointments VetOne has deleted. Running twice, or again after a failure, is harmless.
3. **sql:** the numbered files in `pipeline/sql/` build views on three stored tables: the rules (`02`), counts per clinic and day (`03`), and the report tables (`04`).
4. **check:** stops the run before the export on unknown statuses, unknown clinics, missing times or an active clinic without data. The report then keeps the last good data.
5. **export:** writes the five report tables as Parquet files for Power BI.

Each appointment is judged at the time it was downloaded, so the same download always gives the same result.

**Layout**

```
pipeline/            the pipeline: API client, run command, SQL files
  vetone_api.py      log-in, retries on rate limits and server errors, paging
  run_pipeline.py    the five steps
  sql/               01 tables, 02 rules, 03 clinic-day counts, 04 report views
explore/             the scripts used to explore the API before designing the pipeline
powerbi/             the report as a Power BI Project (text files, no data)
data/                raw downloads and the DuckDB file (not committed)
```

## Assumptions

- **300 minutes:** 99% of completed visits are marked within about 260 minutes of the start. About 4% of the no-shows shown for yesterday at 06:00 are visits marked later, and they correct themselves within days.
- **24 hours** for a late cancellation is an assumption to agree with Nordvet. It is one line in `02_appointment_status.sql`.
- **A cancellation recorded after the start is a no-show.** These are 17% of all no-shows, so this rule matters.
- **"Yesterday" is the last day with appointments.** Clinics are closed on Sundays, so on Mondays it is Saturday.
- **Late updates arrive within 14 days.** All seen so far landed within about 8.
- **Deleted appointments don't count.** The API leaves them out by default.
- **Denmark and Sweden share one clock** (`Europe/Copenhagen`), so one local date works for all clinics.
- **Only active clinics are reported.** CL-420 Ystad is inactive and has no appointments.
- **The API's history starts on 6 August 2026.** Whether that is a fixed start or a rolling window is not known.

## Left out on purpose

- **Vets and patients.** Per-vet numbers are small and the differences follow the clinics, and patient-level lists are personal data. Neither is in the report.
- **Money.** Lost vet hours stand in until Nordvet supplies a price per service.
- **Real-time.** VetOne records no-shows the next working day, so running more often than once a day adds cost but no information.
- **Future bookings.** The view looks backwards. Forecasting no-shows would be a separate project.
- **Alerts and scheduling on the laptop.** The demo runs by hand; on Azure a timer and failure alerts take over.
- **Incremental loading with `updated_since`.** Replacing a 14-day window is simpler and also handles deletions.
- **History of the clinic list.** The current list replaces the old one on every run.
- **Automated tests.** The data checks and the comparison with the pandas rules cover the logic for now.

## Where it would run for Nordvet

Nordvet is on Microsoft 365 and Azure, and their IT team, who will run this after handover, works in SQL and Power BI. The same pieces map onto small, cheap Azure services:

| Laptop | Azure |
|---|---|
| `run_pipeline.py`, started by hand | Azure Function in Python, on a timer at 06:00 Danish time |
| `.env` | Azure Key Vault |
| `data/raw/` | Blob Storage |
| DuckDB file | Azure SQL Database, serverless |
| SQL views, rebuilt on every run | the same views, created once and changed when a rule changes |
| check stops the export | check fails the Function, and an alert email goes to IT |
| Parquet export | not needed: Power BI reads the views directly |
| Power BI Desktop, Refresh by hand | Power BI service, refreshed after the checks have passed |

This would cost roughly €10-30 a month. Power BI is already in use by Nordvet's IT, so the report adds no new tool. Viewing it in the Power BI service needs a Pro licence per viewer, so Mette needs one if she doesn't have it yet. Microsoft Fabric would also fit, but starts at about €250 a month, which is out of proportion to the problem.

The SQL is kept plain so it moves to Azure SQL with small changes:

- `CREATE OR REPLACE VIEW` becomes `CREATE OR ALTER VIEW`, and `CREATE TABLE IF NOT EXISTS` becomes a check on `OBJECT_ID`.
- `BOOLEAN` becomes `BIT`, so `WHERE c.active` becomes `WHERE c.active = 1`, and `TRUE`/`FALSE` become `1`/`0`.
- `x + INTERVAL 300 MINUTE` becomes `DATEADD(minute, 300, x)`, and `run_date - 7` becomes `DATEADD(day, -7, run_date)`.
- `LIMIT 1` becomes `TOP 1`, and `dayname(x)` becomes `DATENAME(weekday, x)`.
- `TIMESTAMP` becomes `DATETIME2`.

In Python, only `load()` changes: it writes to Azure SQL instead of DuckDB, and `export()` is dropped.
