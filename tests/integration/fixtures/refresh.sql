-- Synthetic transaction probes, deliberately not copies of production marts.
CREATE SCHEMA gaia;
CREATE SCHEMA marts;
CREATE SCHEMA integration_probe;
CREATE TABLE integration_probe.control (
    stage text PRIMARY KEY,
    fail boolean NOT NULL DEFAULT false,
    delay_seconds double precision NOT NULL DEFAULT 0
);
INSERT INTO integration_probe.control(stage) VALUES ('summary'), ('sleep'), ('features');
CREATE TABLE integration_probe.writes (
    stage text NOT NULL,
    user_id uuid NOT NULL,
    day date NOT NULL,
    backend_pid integer NOT NULL DEFAULT pg_backend_pid(),
    transaction_id bigint NOT NULL DEFAULT txid_current(),
    statement_timeout text NOT NULL DEFAULT current_setting('statement_timeout'),
    lock_timeout text NOT NULL DEFAULT current_setting('lock_timeout')
);
CREATE TABLE integration_probe.current_snapshot (value integer NOT NULL);
INSERT INTO integration_probe.current_snapshot VALUES (42);
CREATE FUNCTION integration_probe.run_stage(stage_name text, target_user uuid, target_day date)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE settings integration_probe.control%ROWTYPE;
BEGIN
    INSERT INTO integration_probe.writes(stage, user_id, day)
    VALUES (stage_name, target_user, target_day);
    SELECT * INTO STRICT settings FROM integration_probe.control WHERE stage = stage_name;
    IF settings.delay_seconds > 0 THEN
        PERFORM pg_sleep(settings.delay_seconds);
    END IF;
    IF settings.fail THEN
        RAISE EXCEPTION 'injected failure in %', stage_name;
    END IF;
END;
$$;
CREATE FUNCTION gaia.refresh_daily_summary_user(uuid, date, text)
RETURNS void LANGUAGE sql AS $$
    SELECT integration_probe.run_stage('summary', $1, $2);
$$;
CREATE FUNCTION gaia.refresh_daily_summary_sleep_user(uuid, date, text)
RETURNS void LANGUAGE sql AS $$
    SELECT integration_probe.run_stage('sleep', $1, $2);
$$;
CREATE FUNCTION marts.refresh_daily_features_user(uuid, date)
RETURNS void LANGUAGE sql AS $$
    SELECT integration_probe.run_stage('features', $1, $2);
$$;
