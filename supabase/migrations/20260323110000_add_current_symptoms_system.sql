begin;

create table if not exists raw.user_symptom_episodes (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  symptom_event_id uuid not null references raw.user_symptom_events(id) on delete cascade,
  symptom_code text not null references dim.symptom_codes(symptom_code),
  started_at timestamptz not null,
  original_severity smallint check (original_severity between 0 and 10),
  current_severity smallint check (current_severity between 0 and 10),
  current_state text not null default 'new'
    check (current_state in ('new', 'ongoing', 'improving', 'resolved')),
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

create index if not exists user_symptom_episodes_user_state_idx
  on raw.user_symptom_episodes (user_id, current_state, last_interaction_at desc);

create index if not exists user_symptom_episodes_user_started_idx
  on raw.user_symptom_episodes (user_id, started_at desc);

create index if not exists user_symptom_episodes_symptom_code_idx
  on raw.user_symptom_episodes (symptom_code, started_at desc);

alter table raw.user_symptom_episodes enable row level security;

drop policy if exists p_symptom_episode_select on raw.user_symptom_episodes;
create policy p_symptom_episode_select
on raw.user_symptom_episodes
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_symptom_episode_insert on raw.user_symptom_episodes;
create policy p_symptom_episode_insert
on raw.user_symptom_episodes
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_symptom_episode_update on raw.user_symptom_episodes;
create policy p_symptom_episode_update
on raw.user_symptom_episodes
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists p_symptom_episode_delete on raw.user_symptom_episodes;
create policy p_symptom_episode_delete
on raw.user_symptom_episodes
for delete
to authenticated
using (auth.uid() = user_id);

create table if not exists raw.user_symptom_episode_updates (
  id uuid primary key default gen_random_uuid(),
  episode_id uuid not null references raw.user_symptom_episodes(id) on delete cascade,
  user_id uuid not null,
  update_kind text not null default 'state_change'
    check (update_kind in ('logged', 'state_change', 'note', 'severity_update', 'follow_up')),
  state text
    check (state in ('new', 'ongoing', 'improving', 'resolved')),
  severity smallint check (severity between 0 and 10),
  note_text text,
  occurred_at timestamptz not null default now(),
  metadata jsonb not null default '{}'::jsonb,
  source text not null default 'ios',
  created_at timestamptz not null default now()
);

create index if not exists user_symptom_episode_updates_episode_idx
  on raw.user_symptom_episode_updates (episode_id, occurred_at desc);

create index if not exists user_symptom_episode_updates_user_idx
  on raw.user_symptom_episode_updates (user_id, occurred_at desc);

alter table raw.user_symptom_episode_updates enable row level security;

drop policy if exists p_symptom_episode_update_select on raw.user_symptom_episode_updates;
create policy p_symptom_episode_update_select
on raw.user_symptom_episode_updates
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_symptom_episode_update_insert on raw.user_symptom_episode_updates;
create policy p_symptom_episode_update_insert
on raw.user_symptom_episode_updates
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_symptom_episode_update_delete on raw.user_symptom_episode_updates;
create policy p_symptom_episode_update_delete
on raw.user_symptom_episode_updates
for delete
to authenticated
using (auth.uid() = user_id);

insert into raw.user_symptom_episodes (
  user_id,
  symptom_event_id,
  symptom_code,
  started_at,
  original_severity,
  current_severity,
  current_state,
  state_updated_at,
  last_interaction_at,
  latest_note_text,
  latest_note_at,
  source,
  created_at,
  updated_at
)
select
  e.user_id,
  e.id,
  e.symptom_code,
  e.ts_utc,
  e.severity,
  e.severity,
  'new',
  coalesce(e.ts_utc, e.created_at, now()),
  coalesce(e.ts_utc, e.created_at, now()),
  e.free_text,
  case when nullif(btrim(coalesce(e.free_text, '')), '') is null then null else coalesce(e.ts_utc, e.created_at, now()) end,
  coalesce(nullif(btrim(coalesce(e.source, '')), ''), 'ios'),
  coalesce(e.created_at, now()),
  coalesce(e.created_at, now())
from raw.user_symptom_events e
left join raw.user_symptom_episodes ep
  on ep.symptom_event_id = e.id
where ep.id is null;

insert into raw.user_symptom_episode_updates (
  episode_id,
  user_id,
  update_kind,
  state,
  severity,
  note_text,
  occurred_at,
  metadata,
  source,
  created_at
)
select
  ep.id,
  ep.user_id,
  'logged',
  ep.current_state,
  coalesce(ep.current_severity, ep.original_severity),
  ep.latest_note_text,
  ep.started_at,
  jsonb_build_object('symptom_event_id', ep.symptom_event_id),
  ep.source,
  ep.created_at
from raw.user_symptom_episodes ep
where not exists (
  select 1
    from raw.user_symptom_episode_updates u
   where u.episode_id = ep.id
     and u.update_kind = 'logged'
);

alter table if exists app.user_notification_preferences
  add column if not exists symptom_followups_enabled boolean not null default false;

alter table if exists app.user_notification_preferences
  add column if not exists symptom_followup_cadence text not null default 'balanced';

alter table if exists app.user_notification_preferences
  add column if not exists symptom_followup_states text[] not null default array['new', 'ongoing', 'improving']::text[];

alter table if exists app.user_notification_preferences
  add column if not exists symptom_followup_symptom_codes text[] not null default array[]::text[];

do $$
begin
  if not exists (
    select 1
      from pg_constraint
     where conname = 'user_notification_preferences_symptom_followup_cadence_check'
  ) then
    alter table app.user_notification_preferences
      add constraint user_notification_preferences_symptom_followup_cadence_check
      check (symptom_followup_cadence in ('gentle', 'balanced', 'frequent'));
  end if;
end
$$;

alter table if exists app.user_notification_preferences
  alter column families set default jsonb_build_object(
    'geomagnetic', true,
    'solar_wind', true,
    'flare_cme_sep', true,
    'schumann', true,
    'pressure', true,
    'aqi', true,
    'temp', true,
    'gauge_spikes', true,
    'symptom_followups', false
  );

update app.user_notification_preferences
   set families = coalesce(families, '{}'::jsonb) || jsonb_build_object(
     'symptom_followups',
     coalesce(
       case
         when families ? 'symptom_followups' then (families ->> 'symptom_followups')::boolean
         else null
       end,
       symptom_followups_enabled,
       false
     )
   ),
       updated_at = now()
 where not (coalesce(families, '{}'::jsonb) ? 'symptom_followups');

commit;
