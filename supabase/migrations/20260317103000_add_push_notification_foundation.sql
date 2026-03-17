begin;

create schema if not exists app;
create schema if not exists content;

create table if not exists app.user_notification_preferences (
  user_id uuid primary key,
  enabled boolean not null default false,
  signal_alerts_enabled boolean not null default true,
  local_condition_alerts_enabled boolean not null default true,
  personalized_gauge_alerts_enabled boolean not null default true,
  quiet_hours_enabled boolean not null default false,
  quiet_start time not null default time '22:00',
  quiet_end time not null default time '08:00',
  time_zone text not null default 'UTC',
  sensitivity text not null default 'normal'
    check (sensitivity in ('minimal', 'normal', 'detailed')),
  families jsonb not null default jsonb_build_object(
    'geomagnetic', true,
    'solar_wind', true,
    'flare_cme_sep', true,
    'schumann', true,
    'pressure', true,
    'aqi', true,
    'temp', true,
    'gauge_spikes', true
  ),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table app.user_notification_preferences enable row level security;

drop policy if exists p_user_notification_preferences_select on app.user_notification_preferences;
create policy p_user_notification_preferences_select
on app.user_notification_preferences
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_user_notification_preferences_insert on app.user_notification_preferences;
create policy p_user_notification_preferences_insert
on app.user_notification_preferences
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_user_notification_preferences_update on app.user_notification_preferences;
create policy p_user_notification_preferences_update
on app.user_notification_preferences
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create table if not exists app.user_push_tokens (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  platform text not null default 'ios'
    check (platform in ('ios')),
  device_token text not null,
  app_version text null,
  environment text not null default 'prod'
    check (environment in ('dev', 'prod')),
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now()
);

create unique index if not exists user_push_tokens_user_device_token_uidx
  on app.user_push_tokens (user_id, device_token);

create index if not exists user_push_tokens_enabled_user_idx
  on app.user_push_tokens (enabled, user_id, environment);

create index if not exists user_push_tokens_device_token_idx
  on app.user_push_tokens (device_token);

alter table app.user_push_tokens enable row level security;

drop policy if exists p_user_push_tokens_select on app.user_push_tokens;
create policy p_user_push_tokens_select
on app.user_push_tokens
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_user_push_tokens_insert on app.user_push_tokens;
create policy p_user_push_tokens_insert
on app.user_push_tokens
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_user_push_tokens_update on app.user_push_tokens;
create policy p_user_push_tokens_update
on app.user_push_tokens
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists p_user_push_tokens_delete on app.user_push_tokens;
create policy p_user_push_tokens_delete
on app.user_push_tokens
for delete
to authenticated
using (auth.uid() = user_id);

create table if not exists content.push_notification_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  family text not null,
  event_key text not null,
  severity text not null
    check (severity in ('info', 'watch', 'high')),
  title text not null,
  body text not null,
  payload jsonb not null default '{}'::jsonb,
  dedupe_key text not null,
  status text not null default 'queued'
    check (status in ('queued', 'sent', 'skipped', 'failed')),
  created_at timestamptz not null default now(),
  sent_at timestamptz null,
  error_text text null
);

create unique index if not exists push_notification_events_dedupe_uidx
  on content.push_notification_events (dedupe_key);

create index if not exists push_notification_events_status_created_idx
  on content.push_notification_events (status, created_at);

create index if not exists push_notification_events_user_created_idx
  on content.push_notification_events (user_id, created_at desc);

alter table content.push_notification_events enable row level security;

drop policy if exists p_push_notification_events_select on content.push_notification_events;
create policy p_push_notification_events_select
on content.push_notification_events
for select
to authenticated
using (auth.uid() = user_id);

commit;
