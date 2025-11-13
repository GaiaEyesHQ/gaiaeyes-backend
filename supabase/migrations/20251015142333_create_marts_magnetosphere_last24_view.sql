CREATE SCHEMA IF NOT EXISTS ext;
CREATE SCHEMA IF NOT EXISTS marts;

CREATE TABLE IF NOT EXISTS ext.magnetosphere_pulse (
    ts timestamptz NOT NULL,
    n_cm3 double precision,
    v_kms double precision,
    bz_nt double precision,
    pdyn_npa double precision,
    r0_re double precision,
    symh_est integer,
    dbdt_proxy double precision,
    trend_r0 text,
    geo_risk text,
    kpi_bucket text,
    lpp_re double precision,
    kp_latest double precision,
    CONSTRAINT magnetosphere_pulse_pkey PRIMARY KEY (ts)
);

CREATE OR REPLACE VIEW marts.magnetosphere_last_24h AS
SELECT ts, r0_re, kp_latest
FROM ext.magnetosphere_pulse
WHERE ts > now() - interval '24 hours'
ORDER BY ts ASC;

ALTER VIEW marts.magnetosphere_last_24h OWNER TO postgres;
