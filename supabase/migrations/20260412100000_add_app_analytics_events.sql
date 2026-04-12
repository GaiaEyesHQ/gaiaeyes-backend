begin;

create table if not exists raw.app_analytics_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  client_event_id text null,
  event_name text not null
    check (length(event_name) between 1 and 96),
  event_ts_utc timestamptz not null default now(),
  received_at timestamptz not null default now(),
  platform text not null default 'ios'
    check (length(platform) between 1 and 32),
  app_version text null
    check (app_version is null or length(app_version) <= 64),
  device_model text null
    check (device_model is null or length(device_model) <= 96),
  session_id text null
    check (session_id is null or length(session_id) <= 96),
  surface text null
    check (surface is null or length(surface) <= 64),
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists app_analytics_events_user_client_idx
  on raw.app_analytics_events (user_id, client_event_id)
  where client_event_id is not null;

create index if not exists app_analytics_events_ts_idx
  on raw.app_analytics_events (event_ts_utc desc);

create index if not exists app_analytics_events_user_ts_idx
  on raw.app_analytics_events (user_id, event_ts_utc desc);

create index if not exists app_analytics_events_name_ts_idx
  on raw.app_analytics_events (event_name, event_ts_utc desc);

create index if not exists app_analytics_events_props_gin
  on raw.app_analytics_events using gin (properties);

alter table raw.app_analytics_events enable row level security;

drop policy if exists p_app_analytics_events_select on raw.app_analytics_events;
create policy p_app_analytics_events_select
on raw.app_analytics_events
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_app_analytics_events_insert on raw.app_analytics_events;
create policy p_app_analytics_events_insert
on raw.app_analytics_events
for insert
to authenticated
with check (auth.uid() = user_id);

commit;
