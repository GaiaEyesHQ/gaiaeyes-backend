alter table if exists marts.daily_features
  add column if not exists ulf_context_class_raw text,
  add column if not exists ulf_context_label text,
  add column if not exists ulf_confidence_score double precision,
  add column if not exists ulf_confidence_label text,
  add column if not exists ulf_regional_intensity double precision,
  add column if not exists ulf_regional_coherence double precision,
  add column if not exists ulf_regional_persistence double precision,
  add column if not exists ulf_quality_flags jsonb not null default '[]'::jsonb,
  add column if not exists ulf_is_provisional boolean not null default false,
  add column if not exists ulf_is_usable boolean not null default false,
  add column if not exists ulf_is_high_confidence boolean not null default false,
  add column if not exists ulf_station_count integer,
  add column if not exists ulf_missing_samples boolean not null default false,
  add column if not exists ulf_low_history boolean not null default false;

create or replace function marts.refresh_daily_features_user(
  p_user_id uuid,
  p_day date,
  p_days_back integer default 1
) returns void
language plpgsql
as $$
declare
  v_window_end date := coalesce(p_day, current_date);
  v_days_back integer := greatest(coalesce(p_days_back, 1), 1);
  v_window_start date := v_window_end - (v_days_back - 1);
begin
  if p_user_id is null then
    return;
  end if;

  with s as (
    select
      user_id,
      date::date as day,
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
      cycle_day
    from gaia.daily_summary
    where user_id = p_user_id
      and date >= v_window_start
      and date <= v_window_end
  ),
  wx as (
    select
      day,
      kp_max,
      bz_min,
      sw_speed_avg,
      flares_count,
      cmes_count
    from marts.space_weather_daily
    where day >= v_window_start
      and day <= v_window_end
  ),
  sch_t as (
    select
      day,
      f0_avg_hz as t_f0,
      f1_avg_hz as t_f1,
      f2_avg_hz as t_f2,
      f3_avg_hz as t_f3,
      f4_avg_hz as t_f4,
      f5_avg_hz as t_f5
    from marts.schumann_daily
    where station_id = 'tomsk'
      and day >= v_window_start
      and day <= v_window_end
  ),
  sch_c as (
    select
      day,
      f0_avg_hz as c_f0,
      f1_avg_hz as c_f1,
      f2_avg_hz as c_f2,
      f3_avg_hz as c_f3,
      f4_avg_hz as c_f4,
      f5_avg_hz as c_f5
    from marts.schumann_daily
    where station_id = 'cumiana'
      and day >= v_window_start
      and day <= v_window_end
  )
  insert into marts.daily_features (
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
    kp_max,
    bz_min,
    sw_speed_avg,
    flares_count,
    cmes_count,
    ulf_context_class_raw,
    ulf_context_label,
    ulf_confidence_score,
    ulf_confidence_label,
    ulf_regional_intensity,
    ulf_regional_coherence,
    ulf_regional_persistence,
    ulf_quality_flags,
    ulf_is_provisional,
    ulf_is_usable,
    ulf_is_high_confidence,
    ulf_station_count,
    ulf_missing_samples,
    ulf_low_history,
    schumann_station,
    sch_fundamental_avg_hz,
    sch_f1_avg_hz,
    sch_f2_avg_hz,
    sch_f3_avg_hz,
    sch_f4_avg_hz,
    sch_f5_avg_hz,
    sch_cumiana_station,
    sch_cumiana_fundamental_avg_hz,
    sch_cumiana_f1_avg_hz,
    sch_cumiana_f2_avg_hz,
    sch_cumiana_f3_avg_hz,
    sch_cumiana_f4_avg_hz,
    sch_cumiana_f5_avg_hz,
    sch_any_fundamental_avg_hz,
    sch_any_f1_avg_hz,
    sch_any_f2_avg_hz,
    sch_any_f3_avg_hz,
    sch_any_f4_avg_hz,
    sch_any_f5_avg_hz,
    src,
    updated_at
  )
  select
    s.user_id,
    s.day,
    s.hr_min,
    s.hr_max,
    s.hrv_avg,
    s.steps_total,
    s.sleep_total_minutes,
    s.sleep_rem_minutes,
    s.sleep_core_minutes,
    s.sleep_deep_minutes,
    s.sleep_awake_minutes,
    s.sleep_efficiency,
    s.spo2_avg,
    s.bp_sys_avg,
    s.bp_dia_avg,
    s.respiratory_rate_avg,
    s.respiratory_rate_sleep_avg,
    s.respiratory_rate_baseline_delta,
    s.temperature_deviation,
    s.temperature_deviation_baseline_delta,
    s.temperature_source,
    s.resting_hr_avg,
    s.resting_hr_baseline_delta,
    s.bedtime_consistency_score,
    s.waketime_consistency_score,
    s.sleep_debt_proxy,
    s.sleep_vs_14d_baseline_delta,
    s.cycle_tracking_enabled,
    s.cycle_phase,
    s.menstrual_active,
    s.cycle_day,
    w.kp_max,
    w.bz_min,
    w.sw_speed_avg,
    w.flares_count,
    w.cmes_count,
    ulf.context_class as ulf_context_class_raw,
    case
      when ulf.context_class = 'Active (diffuse)' then 'Active'
      when ulf.context_class = 'Elevated (coherent)' then 'Elevated'
      when ulf.context_class = 'Strong (coherent)' then 'Strong'
      when ulf.context_class = 'Quiet' then 'Quiet'
      else ulf.context_class
    end as ulf_context_label,
    ulf.confidence_score as ulf_confidence_score,
    case
      when ulf.confidence_score is null then null
      when ulf.confidence_score < 0.35 then 'Low'
      when ulf.confidence_score < 0.65 then 'Moderate'
      else 'High'
    end as ulf_confidence_label,
    ulf.regional_intensity as ulf_regional_intensity,
    ulf.regional_coherence as ulf_regional_coherence,
    ulf.regional_persistence as ulf_regional_persistence,
    coalesce(ulf.quality_flags, '[]'::jsonb) as ulf_quality_flags,
    coalesce(ulf.quality_flags, '[]'::jsonb) ? 'low_history' as ulf_is_provisional,
    case
      when ulf.ts_utc is null then false
      when ulf.confidence_score is null then false
      when ulf.confidence_score >= 0.20 then true
      else false
    end as ulf_is_usable,
    case
      when ulf.confidence_score is null then false
      when ulf.confidence_score < 0.65 then false
      when coalesce(ulf.quality_flags, '[]'::jsonb) ? 'low_history' then false
      when coalesce(ulf.quality_flags, '[]'::jsonb) ? 'missing_samples' then false
      else true
    end as ulf_is_high_confidence,
    case
      when ulf.ts_utc is null then null
      else coalesce(cardinality(ulf.stations_used), 0)
    end as ulf_station_count,
    coalesce(ulf.quality_flags, '[]'::jsonb) ? 'missing_samples' as ulf_missing_samples,
    coalesce(ulf.quality_flags, '[]'::jsonb) ? 'low_history' as ulf_low_history,
    case when t.t_f0 is not null then 'tomsk' else null end as schumann_station,
    t.t_f0,
    t.t_f1,
    t.t_f2,
    t.t_f3,
    t.t_f4,
    t.t_f5,
    case when c.c_f0 is not null then 'cumiana' else null end as sch_cumiana_station,
    c.c_f0,
    c.c_f1,
    c.c_f2,
    c.c_f3,
    c.c_f4,
    c.c_f5,
    coalesce(t.t_f0, c.c_f0) as sch_any_fundamental_avg_hz,
    coalesce(t.t_f1, c.c_f1) as sch_any_f1_avg_hz,
    coalesce(t.t_f2, c.c_f2) as sch_any_f2_avg_hz,
    coalesce(t.t_f3, c.c_f3) as sch_any_f3_avg_hz,
    coalesce(t.t_f4, c.c_f4) as sch_any_f4_avg_hz,
    coalesce(t.t_f5, c.c_f5) as sch_any_f5_avg_hz,
    'rollup-v5',
    now()
  from s
  left join wx w on w.day = s.day
  left join sch_t t on t.day = s.day
  left join sch_c c on c.day = s.day
  left join lateral (
    select
      ts_utc,
      stations_used,
      regional_intensity,
      regional_coherence,
      regional_persistence,
      context_class,
      confidence_score,
      coalesce(quality_flags, '[]'::jsonb) as quality_flags
    from marts.ulf_context_5m
    where (ts_utc at time zone 'UTC')::date = s.day
    order by ts_utc desc
    limit 1
  ) ulf on true
  on conflict (user_id, day) do update
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
    kp_max = excluded.kp_max,
    bz_min = excluded.bz_min,
    sw_speed_avg = excluded.sw_speed_avg,
    flares_count = excluded.flares_count,
    cmes_count = excluded.cmes_count,
    ulf_context_class_raw = excluded.ulf_context_class_raw,
    ulf_context_label = excluded.ulf_context_label,
    ulf_confidence_score = excluded.ulf_confidence_score,
    ulf_confidence_label = excluded.ulf_confidence_label,
    ulf_regional_intensity = excluded.ulf_regional_intensity,
    ulf_regional_coherence = excluded.ulf_regional_coherence,
    ulf_regional_persistence = excluded.ulf_regional_persistence,
    ulf_quality_flags = excluded.ulf_quality_flags,
    ulf_is_provisional = excluded.ulf_is_provisional,
    ulf_is_usable = excluded.ulf_is_usable,
    ulf_is_high_confidence = excluded.ulf_is_high_confidence,
    ulf_station_count = excluded.ulf_station_count,
    ulf_missing_samples = excluded.ulf_missing_samples,
    ulf_low_history = excluded.ulf_low_history,
    schumann_station = excluded.schumann_station,
    sch_fundamental_avg_hz = excluded.sch_fundamental_avg_hz,
    sch_f1_avg_hz = excluded.sch_f1_avg_hz,
    sch_f2_avg_hz = excluded.sch_f2_avg_hz,
    sch_f3_avg_hz = excluded.sch_f3_avg_hz,
    sch_f4_avg_hz = excluded.sch_f4_avg_hz,
    sch_f5_avg_hz = excluded.sch_f5_avg_hz,
    sch_cumiana_station = excluded.sch_cumiana_station,
    sch_cumiana_fundamental_avg_hz = excluded.sch_cumiana_fundamental_avg_hz,
    sch_cumiana_f1_avg_hz = excluded.sch_cumiana_f1_avg_hz,
    sch_cumiana_f2_avg_hz = excluded.sch_cumiana_f2_avg_hz,
    sch_cumiana_f3_avg_hz = excluded.sch_cumiana_f3_avg_hz,
    sch_cumiana_f4_avg_hz = excluded.sch_cumiana_f4_avg_hz,
    sch_cumiana_f5_avg_hz = excluded.sch_cumiana_f5_avg_hz,
    sch_any_fundamental_avg_hz = excluded.sch_any_fundamental_avg_hz,
    sch_any_f1_avg_hz = excluded.sch_any_f1_avg_hz,
    sch_any_f2_avg_hz = excluded.sch_any_f2_avg_hz,
    sch_any_f3_avg_hz = excluded.sch_any_f3_avg_hz,
    sch_any_f4_avg_hz = excluded.sch_any_f4_avg_hz,
    sch_any_f5_avg_hz = excluded.sch_any_f5_avg_hz,
    src = excluded.src,
    updated_at = now();
end;
$$;
