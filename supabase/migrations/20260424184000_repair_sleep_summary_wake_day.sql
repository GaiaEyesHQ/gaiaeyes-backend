create or replace function gaia.refresh_daily_summary_sleep_user(
  p_user_id uuid,
  p_day date,
  p_tz text default 'America/Chicago'
) returns void
language plpgsql
as $$
declare
  v_tz text := coalesce(nullif(trim(p_tz), ''), 'America/Chicago');
begin
  with sleep_segments as (
    select
      s.user_id,
      (s.end_time at time zone v_tz)::date as day,
      s.start_time,
      s.end_time,
      lower(coalesce(s.value_text, '')) as value_text,
      case
        when lower(s.type) in ('sleep_rem')
          or (lower(s.type) = 'sleep_stage' and lower(coalesce(s.value_text, '')) = 'rem')
        then 'rem'
        when lower(s.type) in ('sleep_core', 'sleep_light')
          or (lower(s.type) = 'sleep_stage' and lower(coalesce(s.value_text, '')) in ('core', 'light'))
        then 'core'
        when lower(s.type) in ('sleep_deep')
          or (lower(s.type) = 'sleep_stage' and lower(coalesce(s.value_text, '')) = 'deep')
        then 'deep'
        when lower(s.type) in ('sleep_awake')
          or (lower(s.type) = 'sleep_stage' and lower(coalesce(s.value_text, '')) = 'awake')
        then 'awake'
        when lower(s.type) in ('sleep_in_bed', 'sleep_inbed')
          or (lower(s.type) = 'sleep_stage' and lower(coalesce(s.value_text, '')) in ('inbed', 'in_bed'))
        then 'inbed'
        when lower(s.type) in ('sleep', 'sleep_asleep')
          or (lower(s.type) = 'sleep_stage' and lower(coalesce(s.value_text, '')) in ('asleep', 'asleepunspecified', 'asleep_unspecified'))
        then 'asleep'
        else null
      end as stage
    from gaia.samples s
    where s.user_id = p_user_id
      and p_day is not null
      and s.end_time > s.start_time
      and (s.end_time at time zone v_tz)::date = p_day
      and lower(s.type) in (
        'sleep',
        'sleep_asleep',
        'sleep_awake',
        'sleep_core',
        'sleep_deep',
        'sleep_in_bed',
        'sleep_inbed',
        'sleep_light',
        'sleep_rem',
        'sleep_stage'
      )
  ),
  sleep_rows as (
    select
      user_id,
      day,
      sum(case when stage = 'asleep' then extract(epoch from (end_time - start_time)) / 60.0 end) as asleep_m,
      sum(case when stage = 'rem' then extract(epoch from (end_time - start_time)) / 60.0 end) as rem_m,
      sum(case when stage = 'core' then extract(epoch from (end_time - start_time)) / 60.0 end) as core_m,
      sum(case when stage = 'deep' then extract(epoch from (end_time - start_time)) / 60.0 end) as deep_m,
      sum(case when stage = 'awake' then extract(epoch from (end_time - start_time)) / 60.0 end) as awake_m,
      sum(case when stage = 'inbed' then extract(epoch from (end_time - start_time)) / 60.0 end) as inbed_m
    from sleep_segments
    where stage is not null
    group by user_id, day
  ),
  computed as (
    select
      user_id,
      day,
      (coalesce(asleep_m, 0) + coalesce(rem_m, 0) + coalesce(core_m, 0) + coalesce(deep_m, 0))::numeric as sleep_total_minutes,
      rem_m::numeric as sleep_rem_minutes,
      core_m::numeric as sleep_core_minutes,
      deep_m::numeric as sleep_deep_minutes,
      awake_m::numeric as sleep_awake_minutes,
      case
        when (
          coalesce(asleep_m, 0)
          + coalesce(rem_m, 0)
          + coalesce(core_m, 0)
          + coalesce(deep_m, 0)
          + coalesce(awake_m, 0)
          + coalesce(inbed_m, 0)
        ) > 0
        then (
          coalesce(asleep_m, 0)
          + coalesce(rem_m, 0)
          + coalesce(core_m, 0)
          + coalesce(deep_m, 0)
        )
        / (
          coalesce(asleep_m, 0)
          + coalesce(rem_m, 0)
          + coalesce(core_m, 0)
          + coalesce(deep_m, 0)
          + coalesce(awake_m, 0)
          + coalesce(inbed_m, 0)
        )
        else null
      end::numeric as sleep_efficiency
    from sleep_rows
  )
  insert into gaia.daily_summary (
    user_id,
    date,
    sleep_total_minutes,
    sleep_rem_minutes,
    sleep_core_minutes,
    sleep_deep_minutes,
    sleep_awake_minutes,
    sleep_efficiency,
    updated_at
  )
  select
    user_id,
    day,
    sleep_total_minutes,
    sleep_rem_minutes,
    sleep_core_minutes,
    sleep_deep_minutes,
    sleep_awake_minutes,
    sleep_efficiency,
    now()
  from computed
  where sleep_total_minutes > 0
     or coalesce(sleep_awake_minutes, 0) > 0
  on conflict (user_id, date) do update
  set
    sleep_total_minutes = excluded.sleep_total_minutes,
    sleep_rem_minutes = excluded.sleep_rem_minutes,
    sleep_core_minutes = excluded.sleep_core_minutes,
    sleep_deep_minutes = excluded.sleep_deep_minutes,
    sleep_awake_minutes = excluded.sleep_awake_minutes,
    sleep_efficiency = excluded.sleep_efficiency,
    updated_at = now();
end;
$$;

comment on function gaia.refresh_daily_summary_sleep_user(uuid, date, text) is
  'Repairs sleep summary fields using wake-day attribution and counts unspecified asleep segments toward total sleep.';
