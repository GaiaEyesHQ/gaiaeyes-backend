\set ON_ERROR_STOP on

-- Minimal disposable prerequisites for exercising the G-008 migration against
-- real PostgreSQL. The table shapes below are copied from the existing symptom
-- domain migrations; this fixture intentionally does not emulate the complete
-- hosted Supabase stack.

do $$
begin
  if current_database() <> 'gaia_migraine_test'
     or current_setting('gaia.migraine_disposable', true) <> 'true' then
    raise exception 'refusing to load migraine fixture outside disposable database';
  end if;
end
$$;

create role anon nologin;
create role authenticated nologin;

create schema auth;
create schema dim;
create schema raw;

create or replace function auth.uid()
returns uuid
language sql
stable
as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;

grant usage on schema auth, raw to anon, authenticated;
grant execute on function auth.uid() to anon, authenticated;

create table dim.symptom_codes (
  symptom_code text primary key,
  label text not null,
  description text,
  is_active boolean not null default true
);

insert into dim.symptom_codes (symptom_code, label, description)
values ('migraine', 'Migraine', 'Synthetic G-009 migraine fixture');

create table raw.user_symptom_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  ts_utc timestamptz not null,
  symptom_code text not null references dim.symptom_codes(symptom_code),
  severity smallint check (severity between 1 and 5),
  free_text text,
  tags text[],
  source text not null default 'ios',
  created_at timestamptz not null default now()
);

create table raw.user_symptom_episodes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  symptom_event_id uuid not null references raw.user_symptom_events(id) on delete cascade,
  symptom_code text not null references dim.symptom_codes(symptom_code),
  started_at timestamptz not null,
  original_severity smallint check (original_severity between 0 and 10),
  current_severity smallint check (current_severity between 0 and 10),
  current_state text not null default 'new'
    check (current_state in ('new', 'ongoing', 'improving', 'worse', 'resolved')),
  state_updated_at timestamptz not null default now(),
  last_interaction_at timestamptz not null default now(),
  improvement_ts timestamptz,
  resolution_ts timestamptz,
  latest_note_text text,
  latest_note_at timestamptz,
  follow_up_state jsonb not null default '{}'::jsonb,
  source text not null default 'ios',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (symptom_event_id)
);

create table raw.user_symptom_episode_updates (
  id uuid primary key default gen_random_uuid(),
  episode_id uuid not null references raw.user_symptom_episodes(id) on delete cascade,
  user_id uuid not null,
  update_kind text not null default 'state_change'
    check (update_kind in ('logged', 'state_change', 'note', 'severity_update', 'follow_up')),
  state text check (state in ('new', 'ongoing', 'improving', 'worse', 'resolved')),
  severity smallint check (severity between 0 and 10),
  note_text text,
  occurred_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  source text not null default 'ios',
  created_at timestamptz not null default now()
);
