CREATE SCHEMA IF NOT EXISTS marts;

CREATE OR REPLACE VIEW marts.magnetosphere_last_24h AS
SELECT ts, r0_re, kp_latest
FROM ext.magnetosphere_pulse
WHERE ts > now() - interval '24 hours'
ORDER BY ts ASC;

ALTER VIEW marts.magnetosphere_last_24h OWNER TO postgres;
