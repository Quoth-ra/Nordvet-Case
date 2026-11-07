# Nordvet case: a first slice of their data platform

Take-home case for a data engineering interview at Heyra. Nordvet is fictional and the data is synthetic, but the API behaves like a real vendor system. There is no single right answer: the assessment is about the choices made and how they are explained.

## The client

Nordvet runs 38 veterinary clinics across Denmark and Sweden. All clinics use the same practice management system, VetOne, for bookings and patient records.

## The assignment

Build a first working version of the no-show view Mette asked for, on data from the VetOne API. Architecture, data model and run frequency are open. Pick what suits Nordvet, not what is most impressive. It only has to run on a laptop for the live demo, but the README must say where it would run for Nordvet (they are on Microsoft 365 and Azure).

## What the stakeholders said

- **Mette, Head of Operations:** no-shows are costly, and she can't see which clinics have a problem until someone complains. She wants to start every morning knowing how each clinic did yesterday.
- **Anders, Head of Digital:** expects it to be real-time.
- **Karin, CEO:** wants to know where they are losing money, and doesn't want a platform that costs more than the no-shows do.
- **Emil, IT:** a team of two SQL and Power BI people, who will have to run whatever is built after handover.

## Data access

- API: https://vetone-api.kinddesert-e2c4fbdc.westeurope.azurecontainerapps.io
- Docs: https://vetone-api.kinddesert-e2c4fbdc.westeurope.azurecontainerapps.io/docs
- Access until 26 November 2026.
- Credentials are read from `.env` (see `.env.example`). Never commit them or copy them into any other file, including this one.
- Treat the API like a client's production system. It is live, so data keeps arriving during the work.
- The docs don't tell the whole story, so verify behaviour against real responses.
- The API scales down when idle, so the first call can take 20 seconds.

## Deliverables

1. **Code:** a repo link that opens without an invite, or a zip without virtualenvs or data dumps. Include a short README covering how to run it, assumptions, what was left out on purpose, and where it would run for Nordvet. Leave the API credentials out. Send to elin.vangbo@heyra.io by 20:00 the day before the interview.
2. **Findings for Mette:** what the data shows about her clinics, as a simple dashboard or a short list. No slides.
3. **Walkthrough:** run the pipeline live, then go through the code: the choices made, the ones not made, and what would change if the situation changed.

## Constraints

- Plan for 4-5 hours in total, ideally over a few days. It is a first slice, so prioritise rather than add scope.
- The interview is 60 minutes, in person, on the laptop this runs on.
- Heyra doesn't answer questions about Nordvet, the data or what to build. Where something is unclear, decide and write it down.

## Decisions

Log every choice here: what was decided, why, and the alternative considered.

| Decision | Reason | Alternative |
| --- | --- | --- |
| Keep raw API responses unchanged as JSON files in `data/raw/`, never committed | We can always go back to exactly what the API sent, and the case asks for no data dumps in the submission | Save only parsed records, or keep them in a temporary folder outside the project |
| Keep API exploration scripts in `explore/` and commit them | Shows how the API was explored before the pipeline was designed, and the step can be repeated | Throwaway scripts outside the repo |
| Use matplotlib for exploration charts, saved as PNG in `data/plots/` (not committed) | pandas plots with it by default, so the code stays short; files can be viewed and shown without a pop-up window | plotly (interactive, but a bigger package and different syntax), or a pop-up window (nothing saved) |
| Add an `inferred_status` (completed, no_show, late_cancelled, cancelled, pending) next to VetOne's `status`, plus `is_inferred` (true when it differs from VetOne's status) | Staff mark no-shows by hand the next working day (08:00-16:00), so at 07:00 almost none of yesterday's no-shows are in VetOne. Rules on the timestamps give Mette usable numbers that morning, and `is_inferred` keeps confirmed and derived values apart | Report only VetOne's `status` (yesterday shows almost no no-shows), or report the day before yesterday (complete, but a day late) |
| Still `booked` more than 300 minutes after the start = `no_show`; less than that or in the future = `pending` | 99% of completed appointments are marked within 261 minutes. Over 21 days, 49 of 11,548 (0.4%) took longer than 300 minutes, spread across many days: about 4% false no-shows (49 against roughly 1,250), which correct themselves when VetOne updates | A longer threshold (fewer false no-shows, but yesterday's late appointments stay pending at 07:00) |
| Cancelled after the scheduled start = `no_show` | 67 of 386 cancellations came 26-297 minutes after the start; an appointment can't be cancelled once it has started, so these are no-shows recorded as cancelled | Keep them as cancelled (undercounts no-shows) |
| Cancelled less than 24 hours before the start = `late_cancelled` | The slot can rarely be filled again at that notice, so it costs nearly as much as a no-show. 24 hours is an assumption to agree with Nordvet | No separate category, or a different threshold |
| Cancellation rules use `cancelled_at`, not `updated_at` | `cancelled_at` is exactly the moment of cancellation and stays correct if VetOne later changes the record again | `updated_at` (identical today, but could change) |
| Rules are evaluated at the time of the download, not the time the script runs | The result always matches the data it was computed from and can be reproduced on old downloads | The current time (results would change every time the script runs on the same data) |
| No-show rate = `no_show / (completed + no_show)` on `inferred_status`; `pending` is left out and shown as its own count; late cancellations are shown next to the rate, not inside it | Answers "of the clients who were expected, how many didn't come", the usual definition in healthcare scheduling. Cancellations and unknown outcomes don't dilute it. `pending` only exists for today (300 minutes after the last appointment at 17:15 everything is decided), so yesterday's 07:00 view never has any. Keeping late cancellations apart keeps the rate free of the 24-hour assumption | No-shows out of all appointments (diluted by cancellations and pending), or lost slots `(no_show + late_cancelled) / (completed + no_show + late_cancelled)` (closer to lost money, but mixes two problems) |
| Use pandas for exploring the data in Python | Standard, readable table library, close to PySpark DataFrames | DuckDB with SQL (would pick the database before the pipeline is designed), or plain Python (more code, harder to read) |
