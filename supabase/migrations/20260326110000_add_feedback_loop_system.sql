begin;

do $$
begin
  update app.user_notification_preferences
     set symptom_followup_cadence = case symptom_followup_cadence
       when 'gentle' then 'minimal'
       when 'frequent' then 'detailed'
       else symptom_followup_cadence
     end
   where symptom_followup_cadence in ('gentle', 'frequent');
exception
  when undefined_table then
    null;
end
$$;

do $$
begin
  if exists (
    select 1
      from pg_constraint
     where conname = 'user_symptom_episodes_current_state_check'
       and conrelid = 'raw.user_symptom_episodes'::regclass
  ) then
    alter table raw.user_symptom_episodes
      drop constraint user_symptom_episodes_current_state_check;
  end if;
end
$$;

alter table if exists raw.user_symptom_episodes
  add constraint user_symptom_episodes_current_state_check
  check (current_state in ('new', 'ongoing', 'improving', 'worse', 'resolved'));

do $$
begin
  if exists (
    select 1
      from pg_constraint
     where conname = 'user_symptom_episode_updates_state_check'
       and conrelid = 'raw.user_symptom_episode_updates'::regclass
  ) then
    alter table raw.user_symptom_episode_updates
      drop constraint user_symptom_episode_updates_state_check;
  end if;
end
$$;

alter table if exists raw.user_symptom_episode_updates
  add constraint user_symptom_episode_updates_state_check
  check (state is null or state in ('new', 'ongoing', 'improving', 'worse', 'resolved'));

alter table if exists app.user_notification_preferences
  add column if not exists symptom_followup_push_enabled boolean not null default false;

alter table if exists app.user_notification_preferences
  add column if not exists daily_checkins_enabled boolean not null default false;

alter table if exists app.user_notification_preferences
  add column if not exists daily_checkin_push_enabled boolean not null default false;

alter table if exists app.user_notification_preferences
  add column if not exists daily_checkin_cadence text not null default 'balanced';

alter table if exists app.user_notification_preferences
  add column if not exists daily_checkin_reminder_time time not null default time '20:00';

do $$
begin
  if exists (
    select 1
      from pg_constraint
     where conname = 'user_notification_preferences_symptom_followup_cadence_check'
  ) then
    alter table app.user_notification_preferences
      drop constraint user_notification_preferences_symptom_followup_cadence_check;
  end if;
exception
  when undefined_table then
    null;
end
$$;

do $$
begin
  if exists (
    select 1
      from information_schema.tables
     where table_schema = 'app'
       and table_name = 'user_notification_preferences'
  ) then
    alter table app.user_notification_preferences
      add constraint user_notification_preferences_symptom_followup_cadence_check
      check (symptom_followup_cadence in ('minimal', 'balanced', 'detailed'));
  end if;
exception
  when duplicate_object then
    null;
end
$$;

do $$
begin
  if not exists (
    select 1
      from pg_constraint
     where conname = 'user_notification_preferences_daily_checkin_cadence_check'
  ) then
    alter table app.user_notification_preferences
      add constraint user_notification_preferences_daily_checkin_cadence_check
      check (daily_checkin_cadence in ('minimal', 'balanced', 'detailed'));
  end if;
exception
  when undefined_table then
    null;
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
    'symptom_followups', false,
    'daily_checkins', false
  );

update app.user_notification_preferences
   set families = coalesce(families, '{}'::jsonb)
       || jsonb_build_object(
         'symptom_followups',
         coalesce(
           case
             when coalesce(families, '{}'::jsonb) ? 'symptom_followups'
               then (families ->> 'symptom_followups')::boolean
             else null
           end,
           symptom_followups_enabled,
           false
         ),
         'daily_checkins',
         coalesce(
           case
             when coalesce(families, '{}'::jsonb) ? 'daily_checkins'
               then (families ->> 'daily_checkins')::boolean
             else null
           end,
           daily_checkins_enabled,
           false
         )
       ),
       updated_at = now()
 where not (
   coalesce(families, '{}'::jsonb) ? 'symptom_followups'
   and coalesce(families, '{}'::jsonb) ? 'daily_checkins'
 );

create table if not exists raw.user_feedback_prompts (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  prompt_type text not null
    check (prompt_type in ('symptom_follow_up', 'daily_check_in')),
  episode_id uuid null references raw.user_symptom_episodes(id) on delete cascade,
  symptom_code text null references dim.symptom_codes(symptom_code),
  prompt_day date null,
  question_key text not null default 'status_check',
  question_text text null,
  prompt_payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'answered', 'dismissed', 'snoozed', 'expired')),
  scheduled_for timestamptz not null default now(),
  delivered_at timestamptz null,
  answered_at timestamptz null,
  dismissed_at timestamptz null,
  snoozed_until timestamptz null,
  response_state text null
    check (response_state in ('ongoing', 'improving', 'worse', 'resolved')),
  response_detail_choice text null,
  response_detail_text text null,
  response_note_text text null,
  response_time_bucket text null,
  push_delivery_enabled boolean not null default false,
  source text not null default 'system',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists user_feedback_prompts_user_status_idx
  on raw.user_feedback_prompts (user_id, status, scheduled_for asc);

create index if not exists user_feedback_prompts_episode_idx
  on raw.user_feedback_prompts (episode_id, scheduled_for desc);

create index if not exists user_feedback_prompts_prompt_day_idx
  on raw.user_feedback_prompts (user_id, prompt_day desc);

create unique index if not exists user_feedback_prompts_episode_pending_uidx
  on raw.user_feedback_prompts (episode_id, prompt_type, question_key)
  where prompt_type = 'symptom_follow_up'
    and status in ('pending', 'snoozed');

create unique index if not exists user_feedback_prompts_daily_pending_uidx
  on raw.user_feedback_prompts (user_id, prompt_day, prompt_type)
  where prompt_type = 'daily_check_in'
    and status in ('pending', 'snoozed');

alter table raw.user_feedback_prompts enable row level security;

drop policy if exists p_user_feedback_prompts_select on raw.user_feedback_prompts;
create policy p_user_feedback_prompts_select
on raw.user_feedback_prompts
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_user_feedback_prompts_insert on raw.user_feedback_prompts;
create policy p_user_feedback_prompts_insert
on raw.user_feedback_prompts
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_user_feedback_prompts_update on raw.user_feedback_prompts;
create policy p_user_feedback_prompts_update
on raw.user_feedback_prompts
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists p_user_feedback_prompts_delete on raw.user_feedback_prompts;
create policy p_user_feedback_prompts_delete
on raw.user_feedback_prompts
for delete
to authenticated
using (auth.uid() = user_id);

create table if not exists raw.user_daily_checkins (
  user_id uuid not null,
  day date not null,
  prompt_id uuid null references raw.user_feedback_prompts(id) on delete set null,
  compared_to_yesterday text not null
    check (compared_to_yesterday in ('better', 'same', 'worse')),
  energy_level text not null
    check (energy_level in ('good', 'manageable', 'low', 'depleted')),
  usable_energy text not null
    check (usable_energy in ('plenty', 'enough', 'limited', 'very_limited')),
  system_load text not null
    check (system_load in ('light', 'moderate', 'heavy', 'overwhelming')),
  pain_level text not null
    check (pain_level in ('none', 'a_little', 'noticeable', 'strong')),
  pain_type text null,
  energy_detail text null,
  mood_level text not null
    check (mood_level in ('calm', 'slightly_off', 'noticeable', 'strong')),
  mood_type text null,
  sleep_impact text null
    check (sleep_impact in ('yes_strongly', 'yes_somewhat', 'not_much', 'unsure')),
  prediction_match text null
    check (prediction_match in ('mostly_right', 'partly_right', 'not_really')),
  note_text text null,
  context_payload jsonb not null default '{}'::jsonb,
  completed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, day)
);

create index if not exists user_daily_checkins_completed_idx
  on raw.user_daily_checkins (user_id, completed_at desc);

alter table raw.user_daily_checkins enable row level security;

drop policy if exists p_user_daily_checkins_select on raw.user_daily_checkins;
create policy p_user_daily_checkins_select
on raw.user_daily_checkins
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_user_daily_checkins_insert on raw.user_daily_checkins;
create policy p_user_daily_checkins_insert
on raw.user_daily_checkins
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_user_daily_checkins_update on raw.user_daily_checkins;
create policy p_user_daily_checkins_update
on raw.user_daily_checkins
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

commit;
