begin;

create table if not exists raw.user_exposure_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  exposure_key text not null
    check (exposure_key in ('overexertion', 'allergen_exposure')),
  intensity smallint not null default 1
    check (intensity between 1 and 3),
  event_ts_utc timestamptz not null default now(),
  source text not null default 'manual'
    check (source in ('manual', 'guide', 'daily_check_in', 'symptom_log', 'system')),
  note_text text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists user_exposure_events_user_ts_idx
  on raw.user_exposure_events (user_id, event_ts_utc desc);

create index if not exists user_exposure_events_user_key_ts_idx
  on raw.user_exposure_events (user_id, exposure_key, event_ts_utc desc);

alter table raw.user_exposure_events enable row level security;

drop policy if exists p_user_exposure_events_select on raw.user_exposure_events;
create policy p_user_exposure_events_select
on raw.user_exposure_events
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists p_user_exposure_events_insert on raw.user_exposure_events;
create policy p_user_exposure_events_insert
on raw.user_exposure_events
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists p_user_exposure_events_update on raw.user_exposure_events;
create policy p_user_exposure_events_update
on raw.user_exposure_events
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists p_user_exposure_events_delete on raw.user_exposure_events;
create policy p_user_exposure_events_delete
on raw.user_exposure_events
for delete
to authenticated
using (auth.uid() = user_id);

do $$
declare
  has_section boolean;
  has_tag_type boolean;
  has_risk_level boolean;
begin
  select exists (
    select 1
      from information_schema.columns
     where table_schema = 'dim'
       and table_name = 'user_tag_catalog'
       and column_name = 'section'
  ) into has_section;

  select exists (
    select 1
      from information_schema.columns
     where table_schema = 'dim'
       and table_name = 'user_tag_catalog'
       and column_name = 'tag_type'
  ) into has_tag_type;

  select exists (
    select 1
      from information_schema.columns
     where table_schema = 'dim'
       and table_name = 'user_tag_catalog'
       and column_name = 'risk_level'
  ) into has_risk_level;

  if has_section then
    insert into dim.user_tag_catalog (tag_key, label, description, section, is_active)
    values ('exertion_recovery_sensitive', 'Exertion / Recovery Sensitive', 'Heavy activity can affect me more, and recovery may take longer.', 'sensitivity', true)
    on conflict (tag_key) do update
    set label = excluded.label,
        description = excluded.description,
        section = excluded.section,
        is_active = excluded.is_active;
  elsif has_tag_type and has_risk_level then
    insert into dim.user_tag_catalog (tag_key, label, tag_type, risk_level, description, is_active)
    values ('exertion_recovery_sensitive', 'Exertion / Recovery Sensitive', 'sensitivity', 'medium', 'Heavy activity can affect me more, and recovery may take longer.', true)
    on conflict (tag_key) do update
    set label = excluded.label,
        tag_type = excluded.tag_type,
        risk_level = excluded.risk_level,
        description = excluded.description,
        is_active = excluded.is_active;
  elsif has_tag_type then
    insert into dim.user_tag_catalog (tag_key, label, tag_type, description, is_active)
    values ('exertion_recovery_sensitive', 'Exertion / Recovery Sensitive', 'sensitivity', 'Heavy activity can affect me more, and recovery may take longer.', true)
    on conflict (tag_key) do update
    set label = excluded.label,
        tag_type = excluded.tag_type,
        description = excluded.description,
        is_active = excluded.is_active;
  else
    insert into dim.user_tag_catalog (tag_key, label, description, is_active)
    values ('exertion_recovery_sensitive', 'Exertion / Recovery Sensitive', 'Heavy activity can affect me more, and recovery may take longer.', true)
    on conflict (tag_key) do update
    set label = excluded.label,
        description = excluded.description,
        is_active = excluded.is_active;
  end if;
end $$;

commit;
