-- Ensure supporting schemas exist
create schema if not exists dim;
create schema if not exists raw;
create schema if not exists marts;

-- Create the lookup table for symptom codes
create table if not exists dim.symptom_codes (
  symptom_code   text primary key,
  label          text not null,
  description    text,
  is_active      boolean not null default true
);

-- Seed the preset symptom codes used by the mobile client (idempotent)
with payload(symptom_code, label, description) as (
  values
    ('nerve_pain', 'Nerve pain', 'Pins/needles, burning, or nerve pain'),
    ('zaps', 'Zaps', 'Electric “zap” sensations'),
    ('drained', 'Drained', 'Sudden drop in energy'),
    ('headache', 'Headache', 'Headache or migraine'),
    ('anxious', 'Anxious', 'Anxiety, jittery, uneasy'),
    ('insomnia', 'Insomnia', 'Difficulty sleeping'),
    ('other', 'Other', 'Other symptom (use notes)')
)
insert into dim.symptom_codes as sc (symptom_code, label, description)
select p.symptom_code, p.label, p.description
from payload p
on conflict (symptom_code) do update
set label = excluded.label,
    description = excluded.description,
    is_active = true;

-- Create the raw event store (idempotent)
create table if not exists raw.user_symptom_events (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null,
  ts_utc         timestamptz not null,
  symptom_code   text not null references dim.symptom_codes(symptom_code),
  severity       smallint check (severity between 1 and 5),
  free_text      text,
  tags           text[],
  source         text not null default 'ios',
  created_at     timestamptz not null default now()
);

create index if not exists user_symptom_events_user_ts_idx
  on raw.user_symptom_events (user_id, ts_utc desc);
create index if not exists user_symptom_events_code_ts_idx
  on raw.user_symptom_events (symptom_code, ts_utc desc);
create index if not exists user_symptom_events_tags_gin
  on raw.user_symptom_events using gin (tags);

alter table raw.user_symptom_events enable row level security;

drop policy if exists p_symptom_insert on raw.user_symptom_events;
create policy p_symptom_insert
on raw.user_symptom_events
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_symptom_select on raw.user_symptom_events;
create policy p_symptom_select
on raw.user_symptom_events
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_symptom_delete on raw.user_symptom_events;
create policy p_symptom_delete
on raw.user_symptom_events
for delete
to authenticated
using (auth.uid() = user_id);

-- Materialized views for reporting (only create if missing)

do $$
begin
  if not exists (
    select 1 from pg_matviews
    where schemaname='marts' and matviewname='symptom_daily'
  ) then
    execute $mv$
      create materialized view marts.symptom_daily as
      with base as (
        select
          (ts_utc at time zone 'UTC')::date as day,
          user_id,
          symptom_code,
          severity,
          ts_utc
        from raw.user_symptom_events
      )
      select
        day,
        user_id,
        symptom_code,
        count(*)                     as events,
        avg(severity::float)         as mean_severity,
        max(ts_utc)                  as last_ts
      from base
      group by day, user_id, symptom_code
      with no data
    $mv$;
    execute 'create unique index if not exists symptom_daily_pk on marts.symptom_daily (day, user_id, symptom_code)';
  end if;
end$$;


do $$
begin
  if not exists (
    select 1 from pg_matviews
    where schemaname='marts' and matviewname='symptom_x_space_daily'
  ) then
    execute $mv$
      create materialized view marts.symptom_x_space_daily as
      with s as (
        select day, user_id,
               sum(events)        as symptom_events,
               avg(mean_severity) as mean_severity
        from marts.symptom_daily
        group by day, user_id
      ),
      sch as (
        select day, avg(f0_avg_hz) as sch_f0_avg
        from marts.schumann_daily
        group by day
      )
      select
        s.day,
        s.user_id,
        s.symptom_events,
        s.mean_severity,
        df.kp_max,
        df.bz_min,
        df.sw_speed_avg,
        sch.sch_f0_avg
      from s
      left join marts.daily_features df
        on df.day = s.day and df.user_id = s.user_id
      left join sch
        on sch.day = s.day
      with no data
    $mv$;
    execute 'create unique index if not exists symptom_x_space_daily_pk on marts.symptom_x_space_daily (day, user_id)';
  end if;
end$$;

-- Refresh the marts so downstream queries stay consistent
refresh materialized view concurrently marts.symptom_daily;
refresh materialized view concurrently marts.symptom_x_space_daily;

-- Helper function for future refresh jobs
create or replace function marts.refresh_symptom_marts()
returns void
language plpgsql
as $$
begin
  refresh materialized view concurrently marts.symptom_daily;
  refresh materialized view concurrently marts.symptom_x_space_daily;
end
$$;
