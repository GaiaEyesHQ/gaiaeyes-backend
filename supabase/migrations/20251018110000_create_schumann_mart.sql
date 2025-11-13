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

do $$
begin
  -- Determine whether any relation already occupies marts.schumann_daily so reruns
  -- gracefully skip creating the materialized view when it exists (as a matview or
  -- legacy table) instead of raising "relation already exists".
  if not exists (
    select 1
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'marts'
      and c.relname = 'schumann_daily'
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
  elsif exists (
    select 1
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'marts'
      and c.relname = 'schumann_daily'
      and c.relkind <> 'm'
  ) then
    raise notice 'marts.schumann_daily already exists as a %; skipping materialized view creation.',
      (select c.relkind
       from pg_catalog.pg_class c
       join pg_catalog.pg_namespace n on n.oid = c.relnamespace
       where n.nspname = 'marts' and c.relname = 'schumann_daily');
  end if;
end$$;

create unique index if not exists schumann_daily_pk
  on marts.schumann_daily (station_id, day);

-- Prime the materialized view so downstream views immediately have data.
do $$
begin
  if exists (
    select 1
    from pg_catalog.pg_class c
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'marts'
      and c.relname = 'schumann_daily'
      and c.relkind = 'm'
  ) then
    execute 'refresh materialized view marts.schumann_daily';
  end if;
end$$;
