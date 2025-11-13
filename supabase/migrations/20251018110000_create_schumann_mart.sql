-- Ensure Schumann ingestion tables and daily mart exist before downstream views reference them.
create schema if not exists ext;
create schema if not exists marts;

create table if not exists ext.schumann_station (
  station_id text primary key,
  name text not null,
  lat double precision,
  lon double precision,
  meta jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists ext.schumann (
  station_id text not null references ext.schumann_station(station_id),
  ts_utc timestamptz not null,
  channel text not null,
  value_num double precision,
  unit text,
  meta jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint schumann_pkey primary key (station_id, ts_utc, channel)
);

create index if not exists schumann_ts_idx on ext.schumann (ts_utc desc);

-- Create the daily mart as a materialized view so analytics queries can reuse it.
do $$
begin
  if not exists (
    select 1 from pg_matviews
    where schemaname='marts' and matviewname='schumann_daily'
  ) then
    execute $mv$
      create materialized view marts.schumann_daily as
      with base as (
        select
          station_id,
          (ts_utc at time zone 'UTC')::date as day,
          channel,
          value_num,
          ts_utc
        from ext.schumann
      )
      select
        station_id,
        day,
        avg(value_num) filter (where channel = 'fundamental_hz') as f0_avg_hz,
        avg(value_num) filter (where channel = 'F1') as f1_avg_hz,
        avg(value_num) filter (where channel = 'F2') as f2_avg_hz,
        avg(value_num) filter (where channel = 'F3') as f3_avg_hz,
        avg(value_num) filter (where channel = 'F4') as f4_avg_hz,
        avg(value_num) filter (where channel = 'F5') as f5_avg_hz,
        count(*) filter (where channel = 'fundamental_hz') as f0_samples,
        max(ts_utc) filter (where channel = 'fundamental_hz') as last_fundamental_ts
      from base
      group by station_id, day
      with no data
    $mv$;
  end if;
end$$;

create unique index if not exists schumann_daily_pk
  on marts.schumann_daily (station_id, day);

-- Prime the materialized view so downstream views immediately have data.
do $$
begin
  if exists (
    select 1 from pg_matviews
    where schemaname='marts' and matviewname='schumann_daily'
  ) then
    execute 'refresh materialized view marts.schumann_daily';
  end if;
end$$;
