begin;

create schema if not exists marts;

create table if not exists marts.local_forecast_daily (
    location_key text not null,
    day date not null,
    source text not null default 'nws:forecast-hourly',
    issued_at timestamptz,
    location_zip text,
    lat double precision,
    lon double precision,
    temp_high_c numeric,
    temp_low_c numeric,
    temp_delta_from_prior_day_c numeric,
    pressure_hpa numeric,
    pressure_delta_from_prior_day_hpa numeric,
    humidity_avg numeric,
    precip_probability numeric,
    wind_speed numeric,
    wind_gust numeric,
    condition_code text,
    condition_summary text,
    aqi_forecast numeric,
    raw jsonb,
    updated_at timestamptz not null default now(),
    primary key (location_key, day)
);

comment on table marts.local_forecast_daily is
  'Normalized 3-day local weather forecast keyed by user location context. Values are nullable when the upstream forecast does not provide a stable daily field.';

create index if not exists local_forecast_daily_day_idx
    on marts.local_forecast_daily (day desc);

create table if not exists marts.space_forecast_daily (
    forecast_day date not null,
    issued_at timestamptz not null,
    source_product_ts timestamptz not null,
    source_src text not null default 'noaa-swpc:3-day-forecast',
    kp_max_forecast numeric,
    g_scale_max text,
    s1_or_greater_pct numeric,
    r1_r2_pct numeric,
    r3_or_greater_pct numeric,
    geomagnetic_rationale text,
    radiation_rationale text,
    radio_rationale text,
    kp_blocks_json jsonb,
    raw_sections_json jsonb,
    flare_watch boolean not null default false,
    cme_watch boolean not null default false,
    solar_wind_watch boolean not null default false,
    geomagnetic_severity_bucket text,
    radiation_severity_bucket text,
    radio_severity_bucket text,
    updated_at timestamptz not null default now(),
    primary key (forecast_day, source_product_ts)
);

comment on table marts.space_forecast_daily is
  'Structured daily parse of the NOAA SWPC 3-day bulletin stored in ext.space_forecast. Keeps daily forecast columns alongside compact JSON for explainable scoring.';

create index if not exists space_forecast_daily_day_idx
    on marts.space_forecast_daily (forecast_day desc, source_product_ts desc);

create or replace view marts.space_forecast_daily_latest as
with ranked as (
    select
        s.*,
        row_number() over (
            partition by s.forecast_day
            order by s.source_product_ts desc, s.updated_at desc
        ) as rn
    from marts.space_forecast_daily s
)
select
    forecast_day,
    issued_at,
    source_product_ts,
    source_src,
    kp_max_forecast,
    g_scale_max,
    s1_or_greater_pct,
    r1_r2_pct,
    r3_or_greater_pct,
    geomagnetic_rationale,
    radiation_rationale,
    radio_rationale,
    kp_blocks_json,
    raw_sections_json,
    flare_watch,
    cme_watch,
    solar_wind_watch,
    geomagnetic_severity_bucket,
    radiation_severity_bucket,
    radio_severity_bucket,
    updated_at
from ranked
where rn = 1;

comment on view marts.space_forecast_daily_latest is
  'Latest parsed SWPC 3-day forecast row per forecast day.';

commit;
