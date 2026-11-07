-- The tables Power BI reads (exported to data/export/*.parquet).
--
-- Rates (in %):
--   no_show_rate      = no_show / (completed + no_show)
--   late_cancel_rate  = late_cancelled / booked
--   cancel_rate       = cancelled / booked   (early cancellations only)
-- Windows, relative to the day of the latest run ("today", which is left out
-- because it isn't over yet):
--   last_day = the last day before today with appointments (Saturday on Mondays)
--   7_days   = the 7 days before today
--   28_days  = the 28 days before today (four full weeks)
-- Only active clinics are listed.
-- On Azure SQL: "LIMIT 1" becomes "TOP 1", "date - 7" becomes "DATEADD(day, -7, date)",
-- and dayname(x) becomes DATENAME(weekday, x).


-- The latest run and the days the report refers to.
CREATE OR REPLACE VIEW report_run AS
WITH latest AS (
    SELECT * FROM runs ORDER BY as_of_utc DESC LIMIT 1
)
SELECT
    l.run_id,
    l.as_of_utc,
    l.run_date,
    (SELECT MAX(scheduled_date) FROM appointments WHERE scheduled_date < l.run_date) AS last_day,
    (SELECT MIN(scheduled_date) FROM appointments) AS data_from
FROM latest AS l;


CREATE OR REPLACE VIEW report_windows AS
SELECT 'last_day' AS window_name, 1 AS window_order, last_day AS date_from, last_day AS date_to FROM report_run
UNION ALL
SELECT '7_days', 2, run_date - 7, run_date - 1 FROM report_run
UNION ALL
SELECT '28_days', 3, run_date - 28, run_date - 1 FROM report_run;


-- One row per clinic and window, with counts and rates.
CREATE OR REPLACE VIEW report_clinic_window AS
WITH sums AS (
    SELECT
        c.clinic_id,
        c.name AS clinic_name,
        c.country,
        w.window_name,
        w.window_order,
        w.date_from,
        w.date_to,
        CAST(SUM(d.booked) AS INTEGER)           AS booked,
        CAST(SUM(d.expected) AS INTEGER)         AS expected,
        CAST(SUM(d.no_show) AS INTEGER)          AS no_show,
        CAST(SUM(d.no_show_inferred) AS INTEGER) AS no_show_inferred,
        CAST(SUM(d.late_cancelled) AS INTEGER)   AS late_cancelled,
        CAST(SUM(d.cancelled) AS INTEGER)        AS cancelled,
        CAST(SUM(d.lost_minutes) AS INTEGER)     AS lost_minutes
    FROM clinics AS c
    CROSS JOIN report_windows AS w
    LEFT JOIN clinic_day AS d
           ON d.clinic_id = c.clinic_id
          AND d.scheduled_date BETWEEN w.date_from AND w.date_to
    WHERE c.active
    GROUP BY c.clinic_id, c.name, c.country, w.window_name, w.window_order, w.date_from, w.date_to
)
SELECT
    *,
    ROUND(100.0 * no_show / NULLIF(expected, 0), 1)      AS no_show_rate_pct,
    ROUND(100.0 * late_cancelled / NULLIF(booked, 0), 1) AS late_cancel_rate_pct,
    ROUND(100.0 * cancelled / NULLIF(booked, 0), 1)      AS cancel_rate_pct,
    ROUND(lost_minutes / 60.0, 1)                        AS lost_vet_hours
FROM sums;


-- The clinic list: one row per clinic, the three windows side by side.
CREATE OR REPLACE VIEW report_clinic_summary AS
SELECT
    clinic_id,
    clinic_name,
    country,
    MAX(CASE WHEN window_name = 'last_day' THEN date_from END)            AS last_day,

    MAX(CASE WHEN window_name = 'last_day' THEN booked END)               AS booked_last_day,
    MAX(CASE WHEN window_name = 'last_day' THEN expected END)             AS expected_last_day,
    MAX(CASE WHEN window_name = 'last_day' THEN no_show END)              AS no_show_last_day,
    MAX(CASE WHEN window_name = 'last_day' THEN no_show_inferred END)     AS no_show_inferred_last_day,
    MAX(CASE WHEN window_name = 'last_day' THEN no_show_rate_pct END)     AS no_show_rate_pct_last_day,
    MAX(CASE WHEN window_name = 'last_day' THEN late_cancel_rate_pct END) AS late_cancel_rate_pct_last_day,
    MAX(CASE WHEN window_name = 'last_day' THEN cancel_rate_pct END)      AS cancel_rate_pct_last_day,
    MAX(CASE WHEN window_name = 'last_day' THEN lost_vet_hours END)       AS lost_vet_hours_last_day,

    MAX(CASE WHEN window_name = '7_days' THEN booked END)                 AS booked_7_days,
    MAX(CASE WHEN window_name = '7_days' THEN expected END)               AS expected_7_days,
    MAX(CASE WHEN window_name = '7_days' THEN no_show END)                AS no_show_7_days,
    MAX(CASE WHEN window_name = '7_days' THEN no_show_rate_pct END)       AS no_show_rate_pct_7_days,
    MAX(CASE WHEN window_name = '7_days' THEN late_cancel_rate_pct END)   AS late_cancel_rate_pct_7_days,
    MAX(CASE WHEN window_name = '7_days' THEN cancel_rate_pct END)        AS cancel_rate_pct_7_days,
    MAX(CASE WHEN window_name = '7_days' THEN lost_vet_hours END)         AS lost_vet_hours_7_days,

    MAX(CASE WHEN window_name = '28_days' THEN booked END)                AS booked_28_days,
    MAX(CASE WHEN window_name = '28_days' THEN expected END)              AS expected_28_days,
    MAX(CASE WHEN window_name = '28_days' THEN no_show END)               AS no_show_28_days,
    MAX(CASE WHEN window_name = '28_days' THEN no_show_rate_pct END)      AS no_show_rate_pct_28_days,
    MAX(CASE WHEN window_name = '28_days' THEN late_cancel_rate_pct END)  AS late_cancel_rate_pct_28_days,
    MAX(CASE WHEN window_name = '28_days' THEN cancel_rate_pct END)       AS cancel_rate_pct_28_days,
    MAX(CASE WHEN window_name = '28_days' THEN lost_vet_hours END)        AS lost_vet_hours_28_days
FROM report_clinic_window
GROUP BY clinic_id, clinic_name, country;


-- Drill-down: each clinic's days in the last 28 days, next to the network.
CREATE OR REPLACE VIEW report_clinic_day AS
WITH network AS (
    SELECT
        scheduled_date,
        ROUND(100.0 * SUM(no_show) / NULLIF(SUM(expected), 0), 1) AS network_no_show_rate_pct
    FROM clinic_day
    GROUP BY scheduled_date
)
SELECT
    d.clinic_id,
    c.name AS clinic_name,
    d.scheduled_date,
    dayname(d.scheduled_date) AS weekday,
    d.booked,
    d.expected,
    d.completed,
    d.no_show,
    d.no_show_inferred,
    d.no_show - d.no_show_inferred AS no_show_confirmed,
    d.late_cancelled,
    d.cancelled,
    ROUND(100.0 * d.no_show / NULLIF(d.expected, 0), 1)      AS no_show_rate_pct,
    ROUND(100.0 * d.late_cancelled / NULLIF(d.booked, 0), 1) AS late_cancel_rate_pct,
    ROUND(100.0 * d.cancelled / NULLIF(d.booked, 0), 1)      AS cancel_rate_pct,
    n.network_no_show_rate_pct
FROM clinic_day AS d
JOIN clinics AS c ON c.clinic_id = d.clinic_id
JOIN network AS n ON n.scheduled_date = d.scheduled_date
CROSS JOIN report_run AS r
WHERE c.active
  AND d.scheduled_date BETWEEN r.run_date - 28 AND r.run_date - 1;


-- Drill-down: each clinic's no-show rate per service in the last 28 days, next to the network.
CREATE OR REPLACE VIEW report_clinic_service AS
WITH last_28 AS (
    SELECT s.*
    FROM appointment_status AS s
    CROSS JOIN report_run AS r
    WHERE s.scheduled_date BETWEEN r.run_date - 28 AND r.run_date - 1
      AND s.inferred_status IN ('completed', 'no_show')
),
network AS (
    SELECT
        service,
        ROUND(100.0 * SUM(CASE WHEN inferred_status = 'no_show' THEN 1 ELSE 0 END) / COUNT(*), 1)
            AS network_no_show_rate_pct
    FROM last_28
    GROUP BY service
)
SELECT
    l.clinic_id,
    c.name AS clinic_name,
    l.service,
    CAST(COUNT(*) AS INTEGER) AS expected,
    CAST(SUM(CASE WHEN l.inferred_status = 'no_show' THEN 1 ELSE 0 END) AS INTEGER) AS no_show,
    ROUND(100.0 * SUM(CASE WHEN l.inferred_status = 'no_show' THEN 1 ELSE 0 END) / COUNT(*), 1)
        AS no_show_rate_pct,
    n.network_no_show_rate_pct
FROM last_28 AS l
JOIN clinics AS c ON c.clinic_id = l.clinic_id
JOIN network AS n ON n.service = l.service
WHERE c.active
GROUP BY l.clinic_id, c.name, l.service, n.network_no_show_rate_pct;
