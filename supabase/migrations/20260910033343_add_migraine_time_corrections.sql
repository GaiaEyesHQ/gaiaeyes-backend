begin;

-- Nullable additions preserve every previous revision and legacy writer.
alter table raw.user_migraine_episode_detail_revisions
  add column if not exists correction_request_id uuid,
  add column if not exists time_correction jsonb;
create unique index if not exists user_migraine_time_correction_request_uidx
  on raw.user_migraine_episode_detail_revisions (user_id, correction_request_id)
  where correction_request_id is not null;
comment on column raw.user_migraine_episode_detail_revisions.time_correction is
  'Normalized time-correction request, before/after canonical timing and refresh dates; assigned only to the new revision in its creating transaction.';

-- A live projection, not another event store. Source timestamps remain intact.
create or replace view raw.user_symptom_events_effective
with (security_invoker = true) as
select e.id, e.user_id,
       coalesce(ep.started_at, e.ts_utc) as ts_utc,
       e.symptom_code, e.severity, e.free_text, e.tags, e.source, e.created_at
  from raw.user_symptom_events e
  left join raw.user_symptom_episodes ep
    on ep.symptom_event_id = e.id and ep.user_id = e.user_id
   and lower(e.symptom_code) = 'migraine' and lower(ep.symptom_code) = 'migraine';
revoke all on raw.user_symptom_events_effective from public, anon;
grant select on raw.user_symptom_events_effective to authenticated;

create schema if not exists marts;
create or replace view marts.symptom_daily_effective
with (security_invoker = true) as
select (ts_utc at time zone 'UTC')::date as day, user_id, symptom_code,
       count(*) as events, avg(severity::float) as mean_severity, max(ts_utc) as last_ts
  from raw.user_symptom_events_effective
 group by 1, 2, 3;
revoke all on marts.symptom_daily_effective from public, anon;
grant usage on schema marts to authenticated;
grant select on marts.symptom_daily_effective to authenticated;

-- Preserve the existing lunar calculation and signature; only switch its input.
do $$
declare definition text;
begin
  if to_regclass('marts.user_lunar_patterns') is not null then
    definition := pg_get_viewdef('marts.user_lunar_patterns'::regclass, true);
    if position('marts.symptom_daily' in definition) > 0
       and position('marts.symptom_daily_effective' in definition) = 0 then
      execute 'create or replace view marts.user_lunar_patterns with (security_invoker = true) as '
        || replace(definition, 'marts.symptom_daily', 'marts.symptom_daily_effective');
    end if;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant select on raw.user_symptom_events_effective, marts.symptom_daily_effective to service_role;
  end if;
end $$;
commit;
