alter table if exists gaia.daily_summary
  add column if not exists respiratory_rate_avg numeric,
  add column if not exists respiratory_rate_sleep_avg numeric,
  add column if not exists respiratory_rate_baseline_delta numeric,
  add column if not exists temperature_deviation numeric,
  add column if not exists temperature_deviation_baseline_delta numeric,
  add column if not exists temperature_source text,
  add column if not exists resting_hr_avg numeric,
  add column if not exists resting_hr_baseline_delta numeric,
  add column if not exists bedtime_consistency_score numeric,
  add column if not exists waketime_consistency_score numeric,
  add column if not exists sleep_debt_proxy numeric,
  add column if not exists sleep_vs_14d_baseline_delta numeric,
  add column if not exists cycle_tracking_enabled boolean not null default false,
  add column if not exists cycle_phase text,
  add column if not exists menstrual_active boolean not null default false,
  add column if not exists cycle_day integer,
  add column if not exists cycle_updated_at timestamptz;

alter table if exists marts.user_daily_features
  add column if not exists respiratory_rate_avg numeric,
  add column if not exists respiratory_rate_sleep_avg numeric,
  add column if not exists respiratory_rate_baseline_delta numeric,
  add column if not exists temperature_deviation numeric,
  add column if not exists temperature_deviation_baseline_delta numeric,
  add column if not exists temperature_source text,
  add column if not exists resting_hr_avg numeric,
  add column if not exists resting_hr_baseline_delta numeric,
  add column if not exists bedtime_consistency_score numeric,
  add column if not exists waketime_consistency_score numeric,
  add column if not exists sleep_debt_proxy numeric,
  add column if not exists sleep_vs_14d_baseline_delta numeric,
  add column if not exists cycle_tracking_enabled boolean not null default false,
  add column if not exists cycle_phase text,
  add column if not exists menstrual_active boolean not null default false,
  add column if not exists cycle_day integer;

alter table if exists marts.user_daily_outcomes
  add column if not exists respiratory_rate_elevated_day boolean,
  add column if not exists resting_hr_elevated_day boolean,
  add column if not exists temperature_deviation_day boolean;

comment on column gaia.daily_summary.cycle_tracking_enabled is
  'True when the user has granted optional cycle tracking and at least one menstrual-flow sample exists in recent history.';

comment on column gaia.daily_summary.temperature_deviation is
  'Daily average temperature-deviation signal from the wearable source when available. Observational only; not diagnostic.';

comment on column gaia.daily_summary.sleep_debt_proxy is
  'Approximate missing sleep minutes versus the prior 14-day personal baseline or a conservative 8-hour fallback.';

create or replace function gaia.refresh_daily_summary_user(
  p_user_id uuid,
  p_day date,
  p_tz text default 'America/Chicago',
  p_days_back integer default 45
) returns void
language plpgsql
as $$
declare
  v_tz text := coalesce(nullif(trim(p_tz), ''), 'America/Chicago');
  v_window_end date := coalesce(p_day, current_date);
  v_days_back integer := greatest(coalesce(p_days_back, 45), 1);
  v_window_start date := v_window_end - (v_days_back - 1);
  v_history_start date := v_window_start - 60;
  v_cycle_start date := v_window_start - 180;
begin
  with raw as (
    select
      s.user_id,
      (s.start_time at time zone v_tz)::date as day_local,
      lower(s.type) as sample_type,
      s.value,
      lower(coalesce(s.value_text, '')) as value_text,
      s.start_time,
      coalesce(s.end_time, s.start_time) as end_time,
      (s.start_time at time zone v_tz) as start_local,
      (coalesce(s.end_time, s.start_time) at time zone v_tz) as end_local
    from gaia.samples s
    where s.user_id = p_user_id
      and (s.start_time at time zone v_tz)::date >= v_cycle_start
      and (s.start_time at time zone v_tz)::date <= v_window_end
  ),
  all_days as (
    select distinct user_id, day_local as day
    from raw
    where day_local >= v_history_start
      and day_local <= v_window_end
  ),
  sleep_segments as (
    select
      user_id,
      day_local,
      start_time,
      end_time,
      start_local,
      end_local,
      case
        when sample_type in ('sleep_rem')
          or (sample_type = 'sleep_stage' and value_text = 'rem')
        then 'rem'
        when sample_type in ('sleep_core', 'sleep_light')
          or (sample_type = 'sleep_stage' and value_text in ('core', 'light'))
        then 'core'
        when sample_type in ('sleep_deep')
          or (sample_type = 'sleep_stage' and value_text = 'deep')
        then 'deep'
        when sample_type in ('sleep_awake')
          or (sample_type = 'sleep_stage' and value_text = 'awake')
        then 'awake'
        when sample_type in ('sleep_in_bed', 'sleep_inbed')
          or (sample_type = 'sleep_stage' and value_text in ('inbed', 'in_bed'))
        then 'inbed'
        when sample_type in ('sleep', 'sleep_asleep')
          or (sample_type = 'sleep_stage' and value_text in ('asleep', 'asleepunspecified'))
        then 'asleep'
        else null
      end as stage
    from raw
    where sample_type in (
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
      day_local as day,
      sum(case when stage = 'rem' then extract(epoch from (end_time - start_time)) / 60.0 end) as rem_m,
      sum(case when stage = 'core' then extract(epoch from (end_time - start_time)) / 60.0 end) as core_m,
      sum(case when stage = 'deep' then extract(epoch from (end_time - start_time)) / 60.0 end) as deep_m,
      sum(case when stage = 'awake' then extract(epoch from (end_time - start_time)) / 60.0 end) as awake_m,
      sum(case when stage = 'inbed' then extract(epoch from (end_time - start_time)) / 60.0 end) as inbed_m
    from sleep_segments
    where stage is not null
    group by user_id, day_local
  ),
  sleep_bounds as (
    select
      user_id,
      day_local as day,
      min(start_local) filter (where stage in ('asleep', 'rem', 'core', 'deep')) as bedtime_local,
      max(end_local) filter (where stage in ('asleep', 'rem', 'core', 'deep')) as waketime_local,
      case
        when min(start_local) filter (where stage in ('asleep', 'rem', 'core', 'deep')) is null then null
        else (
          extract(hour from min(start_local) filter (where stage in ('asleep', 'rem', 'core', 'deep'))) * 60
          + extract(minute from min(start_local) filter (where stage in ('asleep', 'rem', 'core', 'deep')))
          + case
              when (
                extract(hour from min(start_local) filter (where stage in ('asleep', 'rem', 'core', 'deep'))) * 60
                + extract(minute from min(start_local) filter (where stage in ('asleep', 'rem', 'core', 'deep')))
              ) < 720
              then 1440
              else 0
            end
        )::numeric
      end as bedtime_anchor_min,
      case
        when max(end_local) filter (where stage in ('asleep', 'rem', 'core', 'deep')) is null then null
        else (
          extract(hour from max(end_local) filter (where stage in ('asleep', 'rem', 'core', 'deep'))) * 60
          + extract(minute from max(end_local) filter (where stage in ('asleep', 'rem', 'core', 'deep')))
        )::numeric
      end as waketime_anchor_min
    from sleep_segments
    where stage is not null
    group by user_id, day_local
  ),
  agg as (
    select
      user_id,
      day_local as day,
      min(value) filter (where sample_type = 'heart_rate') as hr_min,
      max(value) filter (where sample_type = 'heart_rate') as hr_max,
      avg(value) filter (
        where sample_type in (
          'heart_rate_variability',
          'heart_rate_variability_rmssd',
          'heart_rate_variability_sdnn',
          'hrv',
          'hrv_rmssd',
          'hrv_sdnn',
          'rmssd',
          'sdnn'
        )
      ) as hrv_avg,
      sum(value) filter (where sample_type in ('apple_move_steps', 'step_count', 'steps')) as steps_total,
      avg(value) filter (where sample_type = 'spo2') as spo2_avg,
      avg(value) filter (where sample_type in ('blood_pressure_systolic', 'bp_sys')) as bp_sys_avg,
      avg(value) filter (where sample_type in ('blood_pressure_diastolic', 'bp_dia')) as bp_dia_avg
    from raw
    group by user_id, day_local
  ),
  resp_rows as (
    select
      r.user_id,
      r.day_local as day,
      avg(r.value) as respiratory_rate_avg,
      avg(r.value) filter (
        where exists (
          select 1
          from sleep_segments s
          where s.user_id = r.user_id
            and s.day_local = r.day_local
            and s.stage in ('asleep', 'rem', 'core', 'deep')
            and r.start_time < s.end_time
            and r.end_time > s.start_time
        )
      ) as respiratory_rate_sleep_avg
    from raw r
    where r.sample_type = 'respiratory_rate'
      and r.value is not null
    group by r.user_id, r.day_local
  ),
  resting_hr_rows as (
    select
      user_id,
      day_local as day,
      avg(value) as resting_hr_avg
    from raw
    where sample_type = 'resting_heart_rate'
      and value is not null
    group by user_id, day_local
  ),
  temperature_rows as (
    select
      user_id,
      day_local as day,
      avg(value) as temperature_deviation,
      case
        when max(nullif(value_text, '')) filter (where sample_type = 'temperature_deviation') is not null
        then max(nullif(value_text, '')) filter (where sample_type = 'temperature_deviation')
        when count(*) filter (where sample_type = 'apple_sleeping_wrist_temperature') > 0
        then 'apple_sleeping_wrist_temperature'
        when count(*) filter (where sample_type = 'temperature_deviation') > 0
        then 'temperature_deviation'
        else null
      end as temperature_source
    from raw
    where sample_type in ('apple_sleeping_wrist_temperature', 'temperature_deviation')
      and value is not null
    group by user_id, day_local
  ),
  cycle_active_days as (
    select
      user_id,
      day_local as day,
      true as menstrual_active,
      max(end_time) as cycle_updated_at
    from raw
    where sample_type = 'menstrual_flow'
    group by user_id, day_local
  ),
  cycle_period_starts as (
    select
      user_id,
      day,
      case
        when lag(day) over (partition by user_id order by day) is null then day
        when day - lag(day) over (partition by user_id order by day) > 10 then day
        else null
      end as period_start_day
    from cycle_active_days
  ),
  cycle_rows as (
    select
      d.user_id,
      d.day,
      exists(
        select 1
        from cycle_active_days c
        where c.user_id = d.user_id
          and c.day <= d.day
      ) as cycle_tracking_enabled,
      exists(
        select 1
        from cycle_active_days c
        where c.user_id = d.user_id
          and c.day = d.day
      ) as menstrual_active,
      (
        select max(c.cycle_updated_at)
        from cycle_active_days c
        where c.user_id = d.user_id
          and c.day <= d.day
      ) as cycle_updated_at,
      (
        select max(cps.period_start_day)
        from cycle_period_starts cps
        where cps.user_id = d.user_id
          and cps.period_start_day is not null
          and cps.period_start_day <= d.day
      ) as last_period_start_day
    from all_days d
  ),
  base as (
    select
      d.user_id,
      d.day,
      a.hr_min,
      a.hr_max,
      a.hrv_avg,
      a.steps_total,
      (coalesce(s.rem_m, 0) + coalesce(s.core_m, 0) + coalesce(s.deep_m, 0))::numeric as sleep_total_minutes,
      s.rem_m as sleep_rem_minutes,
      s.core_m as sleep_core_minutes,
      s.deep_m as sleep_deep_minutes,
      s.awake_m as sleep_awake_minutes,
      case
        when (
          coalesce(s.rem_m, 0)
          + coalesce(s.core_m, 0)
          + coalesce(s.deep_m, 0)
          + coalesce(s.awake_m, 0)
          + coalesce(s.inbed_m, 0)
        ) > 0
        then (
          coalesce(s.rem_m, 0)
          + coalesce(s.core_m, 0)
          + coalesce(s.deep_m, 0)
        )
        / (
          coalesce(s.rem_m, 0)
          + coalesce(s.core_m, 0)
          + coalesce(s.deep_m, 0)
          + coalesce(s.awake_m, 0)
          + coalesce(s.inbed_m, 0)
        )
        else null
      end as sleep_efficiency,
      a.spo2_avg,
      a.bp_sys_avg,
      a.bp_dia_avg,
      r.respiratory_rate_avg,
      r.respiratory_rate_sleep_avg,
      t.temperature_deviation,
      t.temperature_source,
      h.resting_hr_avg,
      sb.bedtime_anchor_min,
      sb.waketime_anchor_min,
      c.cycle_tracking_enabled,
      case when c.menstrual_active then 'menstrual' else null end as cycle_phase,
      c.menstrual_active,
      case
        when c.last_period_start_day is not null then (d.day - c.last_period_start_day + 1)
        else null
      end as cycle_day,
      c.cycle_updated_at
    from all_days d
    left join agg a
      on a.user_id = d.user_id
     and a.day = d.day
    left join sleep_rows s
      on s.user_id = d.user_id
     and s.day = d.day
    left join sleep_bounds sb
      on sb.user_id = d.user_id
     and sb.day = d.day
    left join resp_rows r
      on r.user_id = d.user_id
     and r.day = d.day
    left join temperature_rows t
      on t.user_id = d.user_id
     and t.day = d.day
    left join resting_hr_rows h
      on h.user_id = d.user_id
     and h.day = d.day
    left join cycle_rows c
      on c.user_id = d.user_id
     and c.day = d.day
  ),
  scored as (
    select
      b.user_id,
      b.day,
      b.hr_min,
      b.hr_max,
      b.hrv_avg,
      b.steps_total,
      b.sleep_total_minutes,
      b.sleep_rem_minutes,
      b.sleep_core_minutes,
      b.sleep_deep_minutes,
      b.sleep_awake_minutes,
      b.sleep_efficiency,
      b.spo2_avg,
      b.bp_sys_avg,
      b.bp_dia_avg,
      b.respiratory_rate_avg,
      b.respiratory_rate_sleep_avg,
      case
        when resp_base.n >= 3
         and coalesce(b.respiratory_rate_sleep_avg, b.respiratory_rate_avg) is not null
         and resp_base.avg_val is not null
        then round((coalesce(b.respiratory_rate_sleep_avg, b.respiratory_rate_avg) - resp_base.avg_val)::numeric, 3)
        else null
      end as respiratory_rate_baseline_delta,
      b.temperature_deviation,
      case
        when temp_base.n >= 3
         and b.temperature_deviation is not null
         and temp_base.avg_val is not null
        then round((b.temperature_deviation - temp_base.avg_val)::numeric, 3)
        else null
      end as temperature_deviation_baseline_delta,
      b.temperature_source,
      b.resting_hr_avg,
      case
        when resting_hr_base.n >= 3
         and b.resting_hr_avg is not null
         and resting_hr_base.avg_val is not null
        then round((b.resting_hr_avg - resting_hr_base.avg_val)::numeric, 3)
        else null
      end as resting_hr_baseline_delta,
      case
        when bedtime_base.n >= 5
         and b.bedtime_anchor_min is not null
         and bedtime_base.median_val is not null
        then greatest(
          0::numeric,
          least(
            100::numeric,
            round(
              (100 - (abs(b.bedtime_anchor_min - bedtime_base.median_val) / 180.0 * 100))::numeric,
              1
            )
          )
        )
        else null
      end as bedtime_consistency_score,
      case
        when waketime_base.n >= 5
         and b.waketime_anchor_min is not null
         and waketime_base.median_val is not null
        then greatest(
          0::numeric,
          least(
            100::numeric,
            round(
              (100 - (abs(b.waketime_anchor_min - waketime_base.median_val) / 180.0 * 100))::numeric,
              1
            )
          )
        )
        else null
      end as waketime_consistency_score,
      case
        when b.sleep_total_minutes is not null
        then round(greatest(0::numeric, coalesce(sleep_base.avg_val, 480::numeric) - b.sleep_total_minutes)::numeric, 1)
        else null
      end as sleep_debt_proxy,
      case
        when sleep_base.n >= 5
         and b.sleep_total_minutes is not null
         and sleep_base.avg_val is not null
        then round((b.sleep_total_minutes - sleep_base.avg_val)::numeric, 1)
        else null
      end as sleep_vs_14d_baseline_delta,
      coalesce(b.cycle_tracking_enabled, false) as cycle_tracking_enabled,
      b.cycle_phase,
      coalesce(b.menstrual_active, false) as menstrual_active,
      b.cycle_day,
      b.cycle_updated_at
    from base b
    left join lateral (
      select
        avg(coalesce(x.respiratory_rate_sleep_avg, x.respiratory_rate_avg)) as avg_val,
        count(*) as n
      from base x
      where x.user_id = b.user_id
        and x.day >= b.day - 14
        and x.day < b.day
        and coalesce(x.respiratory_rate_sleep_avg, x.respiratory_rate_avg) is not null
    ) resp_base on true
    left join lateral (
      select avg(x.temperature_deviation) as avg_val, count(*) as n
      from base x
      where x.user_id = b.user_id
        and x.day >= b.day - 14
        and x.day < b.day
        and x.temperature_deviation is not null
    ) temp_base on true
    left join lateral (
      select avg(x.resting_hr_avg) as avg_val, count(*) as n
      from base x
      where x.user_id = b.user_id
        and x.day >= b.day - 14
        and x.day < b.day
        and x.resting_hr_avg is not null
    ) resting_hr_base on true
    left join lateral (
      select avg(x.sleep_total_minutes) as avg_val, count(*) as n
      from base x
      where x.user_id = b.user_id
        and x.day >= b.day - 14
        and x.day < b.day
        and x.sleep_total_minutes is not null
    ) sleep_base on true
    left join lateral (
      select
        percentile_cont(0.5) within group (order by x.bedtime_anchor_min) as median_val,
        count(*) as n
      from base x
      where x.user_id = b.user_id
        and x.day >= b.day - 14
        and x.day < b.day
        and x.bedtime_anchor_min is not null
    ) bedtime_base on true
    left join lateral (
      select
        percentile_cont(0.5) within group (order by x.waketime_anchor_min) as median_val,
        count(*) as n
      from base x
      where x.user_id = b.user_id
        and x.day >= b.day - 14
        and x.day < b.day
        and x.waketime_anchor_min is not null
    ) waketime_base on true
  )
  insert into gaia.daily_summary (
    user_id,
    date,
    hr_min,
    hr_max,
    hrv_avg,
    steps_total,
    sleep_total_minutes,
    sleep_rem_minutes,
    sleep_core_minutes,
    sleep_deep_minutes,
    sleep_awake_minutes,
    sleep_efficiency,
    spo2_avg,
    bp_sys_avg,
    bp_dia_avg,
    respiratory_rate_avg,
    respiratory_rate_sleep_avg,
    respiratory_rate_baseline_delta,
    temperature_deviation,
    temperature_deviation_baseline_delta,
    temperature_source,
    resting_hr_avg,
    resting_hr_baseline_delta,
    bedtime_consistency_score,
    waketime_consistency_score,
    sleep_debt_proxy,
    sleep_vs_14d_baseline_delta,
    cycle_tracking_enabled,
    cycle_phase,
    menstrual_active,
    cycle_day,
    cycle_updated_at,
    updated_at
  )
  select
    user_id,
    day,
    hr_min,
    hr_max,
    hrv_avg,
    steps_total,
    sleep_total_minutes,
    sleep_rem_minutes,
    sleep_core_minutes,
    sleep_deep_minutes,
    sleep_awake_minutes,
    sleep_efficiency,
    spo2_avg,
    bp_sys_avg,
    bp_dia_avg,
    respiratory_rate_avg,
    respiratory_rate_sleep_avg,
    respiratory_rate_baseline_delta,
    temperature_deviation,
    temperature_deviation_baseline_delta,
    temperature_source,
    resting_hr_avg,
    resting_hr_baseline_delta,
    bedtime_consistency_score,
    waketime_consistency_score,
    sleep_debt_proxy,
    sleep_vs_14d_baseline_delta,
    cycle_tracking_enabled,
    cycle_phase,
    menstrual_active,
    cycle_day,
    cycle_updated_at,
    now()
  from scored
  where day >= v_window_start
    and day <= v_window_end
  on conflict (user_id, date) do update
  set
    hr_min = excluded.hr_min,
    hr_max = excluded.hr_max,
    hrv_avg = excluded.hrv_avg,
    steps_total = excluded.steps_total,
    sleep_total_minutes = excluded.sleep_total_minutes,
    sleep_rem_minutes = excluded.sleep_rem_minutes,
    sleep_core_minutes = excluded.sleep_core_minutes,
    sleep_deep_minutes = excluded.sleep_deep_minutes,
    sleep_awake_minutes = excluded.sleep_awake_minutes,
    sleep_efficiency = excluded.sleep_efficiency,
    spo2_avg = excluded.spo2_avg,
    bp_sys_avg = excluded.bp_sys_avg,
    bp_dia_avg = excluded.bp_dia_avg,
    respiratory_rate_avg = excluded.respiratory_rate_avg,
    respiratory_rate_sleep_avg = excluded.respiratory_rate_sleep_avg,
    respiratory_rate_baseline_delta = excluded.respiratory_rate_baseline_delta,
    temperature_deviation = excluded.temperature_deviation,
    temperature_deviation_baseline_delta = excluded.temperature_deviation_baseline_delta,
    temperature_source = excluded.temperature_source,
    resting_hr_avg = excluded.resting_hr_avg,
    resting_hr_baseline_delta = excluded.resting_hr_baseline_delta,
    bedtime_consistency_score = excluded.bedtime_consistency_score,
    waketime_consistency_score = excluded.waketime_consistency_score,
    sleep_debt_proxy = excluded.sleep_debt_proxy,
    sleep_vs_14d_baseline_delta = excluded.sleep_vs_14d_baseline_delta,
    cycle_tracking_enabled = excluded.cycle_tracking_enabled,
    cycle_phase = excluded.cycle_phase,
    menstrual_active = excluded.menstrual_active,
    cycle_day = excluded.cycle_day,
    cycle_updated_at = excluded.cycle_updated_at,
    updated_at = now();
end;
$$;
