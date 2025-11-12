-- Step 1 predictive space-weather datasets
-- This migration introduces the ext.* landing tables and marts.* rollups
-- required for the Step 1 roadmap.

begin;

create schema if not exists ext;
create schema if not exists marts;

-- ---------------------------------------------------------------------------
-- ext.enlil_forecast + marts.cme_arrivals
-- ---------------------------------------------------------------------------
create table if not exists ext.enlil_forecast (
    simulation_id text primary key,
    model_run timestamptz,
    activity_id text,
    model_type text,
    impact_count integer,
    raw jsonb not null,
    fetched_at timestamptz not null default now()
);

create index if not exists enlil_forecast_model_run_idx
    on ext.enlil_forecast (model_run desc);

create table if not exists marts.cme_arrivals (
    arrival_time timestamptz not null,
    simulation_id text not null references ext.enlil_forecast(simulation_id) on delete cascade,
    location text,
    location_key text generated always as (coalesce(location, 'global')) stored,
    cme_speed_kms numeric,
    kp_estimate numeric,
    confidence text,
    raw jsonb,
    created_at timestamptz not null default now(),
    primary key (arrival_time, simulation_id, location_key)
);

create index if not exists cme_arrivals_arrival_time_idx
    on marts.cme_arrivals (arrival_time desc);

-- ---------------------------------------------------------------------------
-- GOES proton flux (ext.sep_flux)
-- ---------------------------------------------------------------------------
create table if not exists ext.sep_flux (
    ts_utc timestamptz not null,
    satellite text not null,
    energy_band text not null,
    flux numeric,
    s_scale text,
    s_scale_index integer,
    raw jsonb,
    primary key (ts_utc, satellite, energy_band)
);

create index if not exists sep_flux_s_scale_idx
    on ext.sep_flux (s_scale_index desc nulls last);

-- ---------------------------------------------------------------------------
-- Radiation belt flux + rollup
-- ---------------------------------------------------------------------------
create table if not exists ext.radiation_belts (
    ts_utc timestamptz not null,
    satellite text not null,
    energy_band text not null,
    flux numeric,
    risk_level text,
    raw jsonb,
    primary key (ts_utc, satellite, energy_band)
);

create index if not exists radiation_belts_risk_idx
    on ext.radiation_belts (risk_level, ts_utc desc);

create table if not exists marts.radiation_belts_daily (
    day date not null,
    satellite text not null,
    max_flux numeric,
    avg_flux numeric,
    risk_level text,
    computed_at timestamptz not null default now(),
    primary key (day, satellite)
);

-- ---------------------------------------------------------------------------
-- Aurora + Wing Kp
-- ---------------------------------------------------------------------------
create table if not exists ext.aurora_power (
    ts_utc timestamptz not null,
    hemisphere text not null,
    hemispheric_power_gw numeric,
    wing_kp numeric,
    raw jsonb,
    primary key (ts_utc, hemisphere)
);

create index if not exists aurora_power_ts_idx
    on ext.aurora_power (ts_utc desc);

create table if not exists marts.aurora_outlook (
    valid_from timestamptz not null,
    valid_to timestamptz,
    hemisphere text not null,
    headline text,
    power_gw numeric,
    wing_kp numeric,
    confidence text,
    created_at timestamptz not null default now(),
    primary key (valid_from, hemisphere)
);

-- ---------------------------------------------------------------------------
-- Coronal hole & CME scoreboard
-- ---------------------------------------------------------------------------
create table if not exists ext.ch_forecast (
    forecast_time timestamptz not null,
    source text not null,
    speed_kms numeric,
    density_cm3 numeric,
    raw jsonb,
    primary key (forecast_time, source)
);

create index if not exists ch_forecast_time_idx
    on ext.ch_forecast (forecast_time desc);

create table if not exists ext.cme_scoreboard (
    event_time timestamptz not null,
    team_name text not null,
    scoreboard_id text,
    predicted_arrival timestamptz,
    observed_arrival timestamptz,
    kp_predicted numeric,
    raw jsonb,
    primary key (event_time, team_name)
);

create index if not exists cme_scoreboard_arrival_idx
    on ext.cme_scoreboard (predicted_arrival desc nulls last);

-- ---------------------------------------------------------------------------
-- D-RAP absorption
-- ---------------------------------------------------------------------------
create table if not exists ext.drap_absorption (
    ts_utc timestamptz not null,
    frequency_mhz numeric,
    region text,
    region_key text generated always as (coalesce(region, 'global')) stored,
    frequency_key text generated always as (coalesce(frequency_mhz::text, 'na')) stored,
    absorption_db numeric,
    raw jsonb,
    primary key (ts_utc, region_key, frequency_key)
);

create table if not exists marts.drap_absorption_daily (
    day date not null,
    region text not null,
    max_absorption_db numeric,
    avg_absorption_db numeric,
    created_at timestamptz not null default now(),
    primary key (day, region)
);

-- ---------------------------------------------------------------------------
-- Solar cycle forecast
-- ---------------------------------------------------------------------------
create table if not exists ext.solar_cycle_forecast (
    forecast_month date primary key,
    issued_at timestamptz,
    sunspot_number numeric,
    f10_7_flux numeric,
    raw jsonb
);

create table if not exists marts.solar_cycle_progress (
    forecast_month date primary key,
    issued_at timestamptz,
    sunspot_number numeric,
    f10_7_flux numeric,
    confidence text
);

-- ---------------------------------------------------------------------------
-- Magnetometer chain
-- ---------------------------------------------------------------------------
create table if not exists ext.magnetometer_chain (
    ts_utc timestamptz not null,
    station text not null,
    ae numeric,
    al numeric,
    au numeric,
    pc numeric,
    raw jsonb,
    primary key (ts_utc, station)
);

create index if not exists magnetometer_chain_ts_idx
    on ext.magnetometer_chain (ts_utc desc);

create table if not exists marts.magnetometer_regional (
    ts_utc timestamptz not null,
    region text not null,
    ae numeric,
    al numeric,
    au numeric,
    pc numeric,
    stations jsonb,
    created_at timestamptz not null default now(),
    primary key (ts_utc, region)
);

commit;
