-- Stored tables. Everything after this file is a view on top of them.
-- Timestamps are UTC without a time zone; scheduled_date is the clinic's local date.

CREATE TABLE IF NOT EXISTS runs (
    run_id      VARCHAR PRIMARY KEY,  -- the raw folder name, e.g. run_20261107T120000Z
    as_of_utc   TIMESTAMP NOT NULL,   -- when the data was downloaded; the rules are evaluated at this time
    run_date    DATE NOT NULL,        -- the local date of the download ("today" in the report)
    date_from   DATE NOT NULL,        -- the reloaded window of scheduled dates
    date_to     DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS clinics (
    clinic_id   VARCHAR PRIMARY KEY,
    name        VARCHAR,
    city        VARCHAR,
    country     VARCHAR,
    timezone    VARCHAR,
    active      BOOLEAN,
    opened_on   DATE
);

CREATE TABLE IF NOT EXISTS appointments (
    id                VARCHAR PRIMARY KEY,
    clinic_id         VARCHAR NOT NULL,
    vet_id            VARCHAR,
    patient_ref       VARCHAR,
    service           VARCHAR,
    scheduled_date    DATE NOT NULL,
    scheduled_at_utc  TIMESTAMP NOT NULL,
    duration_minutes  INTEGER,
    status            VARCHAR NOT NULL,   -- VetOne's own status
    created_at_utc    TIMESTAMP,
    updated_at_utc    TIMESTAMP,
    cancelled_at_utc  TIMESTAMP,
    run_id            VARCHAR NOT NULL     -- the run this version came from
);
