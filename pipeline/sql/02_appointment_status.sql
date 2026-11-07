-- inferred_status: VetOne staff record no-shows by hand the next working day,
-- so these rules use the timestamps to give the status earlier.
--
--   VetOne status  condition                                       inferred_status
--   completed                                                      completed
--   no_show                                                        no_show
--   booked         more than 300 minutes after the start           no_show
--   booked         less than that, or in the future                pending
--   cancelled      cancelled after the start                       no_show
--   cancelled      cancelled less than 24 hours before the start   late_cancelled
--   cancelled      cancelled earlier                               cancelled
--
-- 300 minutes: 99% of completed appointments are marked within about 260.
-- 24 hours: an assumption to agree with Nordvet.
-- Each appointment is judged at the time it was downloaded (runs.as_of_utc),
-- so the result always matches the data it was computed from.
-- On Azure SQL: "x + INTERVAL 300 MINUTE" becomes "DATEADD(minute, 300, x)".

CREATE OR REPLACE VIEW appointment_status AS
WITH rules AS (
    SELECT
        a.*,
        r.as_of_utc,
        CASE
            WHEN a.status IN ('completed', 'no_show') THEN a.status
            WHEN a.status = 'booked'
                 AND r.as_of_utc > a.scheduled_at_utc + INTERVAL 300 MINUTE THEN 'no_show'
            WHEN a.status = 'booked' THEN 'pending'
            WHEN a.status = 'cancelled'
                 AND a.cancelled_at_utc > a.scheduled_at_utc THEN 'no_show'
            WHEN a.status = 'cancelled'
                 AND a.cancelled_at_utc > a.scheduled_at_utc - INTERVAL 1440 MINUTE THEN 'late_cancelled'
            WHEN a.status = 'cancelled' THEN 'cancelled'
            ELSE 'unknown'  -- a status we haven't seen before: flag it rather than guess
        END AS inferred_status
    FROM appointments AS a
    JOIN runs AS r ON r.run_id = a.run_id
)
SELECT
    *,
    CASE WHEN inferred_status <> status THEN TRUE ELSE FALSE END AS is_inferred
FROM rules;
