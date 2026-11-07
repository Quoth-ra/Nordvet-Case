-- One row per clinic and day: counts only. Rates are always computed from
-- summed counts (never by averaging daily rates), so they stay correct over any window.
-- Counts are cast to INTEGER: SUM alone gives a 128-bit integer, which the
-- Parquet export would turn into a decimal number.
--
--   booked    = every appointment whose outcome is known (all but pending)
--   expected  = completed + no_show: the clients who were expected to come

CREATE OR REPLACE VIEW clinic_day AS
SELECT
    clinic_id,
    scheduled_date,
    CAST(COUNT(*) AS INTEGER)                                                 AS appointments,
    CAST(SUM(CASE WHEN inferred_status <> 'pending' THEN 1 ELSE 0 END) AS INTEGER)             AS booked,
    CAST(SUM(CASE WHEN inferred_status IN ('completed', 'no_show') THEN 1 ELSE 0 END) AS INTEGER) AS expected,
    CAST(SUM(CASE WHEN inferred_status = 'completed' THEN 1 ELSE 0 END) AS INTEGER)            AS completed,
    CAST(SUM(CASE WHEN inferred_status = 'no_show' THEN 1 ELSE 0 END) AS INTEGER)              AS no_show,
    CAST(SUM(CASE WHEN inferred_status = 'no_show' AND is_inferred THEN 1 ELSE 0 END) AS INTEGER) AS no_show_inferred,
    CAST(SUM(CASE WHEN inferred_status = 'late_cancelled' THEN 1 ELSE 0 END) AS INTEGER)       AS late_cancelled,
    CAST(SUM(CASE WHEN inferred_status = 'cancelled' THEN 1 ELSE 0 END) AS INTEGER)            AS cancelled,
    CAST(SUM(CASE WHEN inferred_status = 'pending' THEN 1 ELSE 0 END) AS INTEGER)              AS pending,
    -- Lost vet time: the booked minutes of no-shows and late cancellations.
    CAST(SUM(CASE WHEN inferred_status IN ('no_show', 'late_cancelled')
             THEN duration_minutes ELSE 0 END) AS INTEGER)                                AS lost_minutes
FROM appointment_status
GROUP BY clinic_id, scheduled_date;
