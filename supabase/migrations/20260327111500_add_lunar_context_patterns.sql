begin;

alter table if exists marts.daily_features
  add column if not exists moon_phase_fraction numeric,
  add column if not exists moon_illumination_pct numeric,
  add column if not exists moon_phase_label text,
  add column if not exists days_from_full_moon integer,
  add column if not exists days_from_new_moon integer;

alter table if exists app.user_experience_profiles
  add column if not exists lunar_sensitivity_declared boolean not null default false;

create or replace function marts.lunar_context_for_day(p_day date)
returns table (
  moon_phase_fraction numeric,
  moon_illumination_pct numeric,
  moon_phase_label text,
  days_from_full_moon integer,
  days_from_new_moon integer
)
language sql
immutable
as $$
with constants as (
  select
    timestamptz '2000-01-06 18:14:00+00' as known_new_moon,
    29.53058867::double precision as synodic_days,
    (
      make_timestamptz(
        extract(year from p_day)::integer,
        extract(month from p_day)::integer,
        extract(day from p_day)::integer,
        12,
        0,
        0,
        'UTC'
      )
    ) as day_mid_utc
),
phase as (
  select
    known_new_moon,
    synodic_days,
    day_mid_utc,
    (
      (extract(epoch from (day_mid_utc - known_new_moon)) / 86400.0) / synodic_days
      - floor((extract(epoch from (day_mid_utc - known_new_moon)) / 86400.0) / synodic_days)
    ) as cycle
  from constants
),
events as (
  select
    day_mid_utc,
    cycle,
    0.5 * (1 - cos(2 * pi() * cycle)) as illumination_fraction,
    (
      known_new_moon
      + (
        round(
          (extract(epoch from (day_mid_utc - known_new_moon)) / 86400.0) / synodic_days
        ) * synodic_days
      ) * interval '1 day'
    ) as nearest_new_moon_utc,
    (
      known_new_moon
      + (synodic_days / 2.0) * interval '1 day'
      + (
        round(
          (
            extract(
              epoch
              from (
                day_mid_utc
                - (
                  known_new_moon
                  + (synodic_days / 2.0) * interval '1 day'
                )
              )
            ) / 86400.0
          ) / synodic_days
        ) * synodic_days
      ) * interval '1 day'
    ) as nearest_full_moon_utc
  from phase
)
select
  round(cycle::numeric, 6) as moon_phase_fraction,
  round((illumination_fraction * 100.0)::numeric, 3) as moon_illumination_pct,
  case
    when cycle >= 0.77 then 'Waning Crescent'
    when cycle >= 0.73 then 'Last Quarter'
    when cycle >= 0.52 then 'Waning Gibbous'
    when cycle >= 0.47 then 'Full Moon'
    when cycle >= 0.27 then 'Waxing Gibbous'
    when cycle >= 0.23 then 'First Quarter'
    when cycle >= 0.03 then 'Waxing Crescent'
    else 'New Moon'
  end as moon_phase_label,
  round(extract(epoch from (day_mid_utc - nearest_full_moon_utc)) / 86400.0)::integer as days_from_full_moon,
  round(extract(epoch from (day_mid_utc - nearest_new_moon_utc)) / 86400.0)::integer as days_from_new_moon
from events;
$$;

with lunar_by_day as (
  select distinct
    df_source.day,
    lunar.moon_phase_fraction,
    lunar.moon_illumination_pct,
    lunar.moon_phase_label,
    lunar.days_from_full_moon,
    lunar.days_from_new_moon
  from marts.daily_features as df_source
  cross join lateral marts.lunar_context_for_day(df_source.day) as lunar
  where df_source.day is not null
)
update marts.daily_features as df
set
  moon_phase_fraction = lunar_by_day.moon_phase_fraction,
  moon_illumination_pct = lunar_by_day.moon_illumination_pct,
  moon_phase_label = lunar_by_day.moon_phase_label,
  days_from_full_moon = lunar_by_day.days_from_full_moon,
  days_from_new_moon = lunar_by_day.days_from_new_moon
from lunar_by_day
where lunar_by_day.day = df.day
  and (
    df.moon_phase_fraction is distinct from lunar_by_day.moon_phase_fraction
    or df.moon_illumination_pct is distinct from lunar_by_day.moon_illumination_pct
    or df.moon_phase_label is distinct from lunar_by_day.moon_phase_label
    or df.days_from_full_moon is distinct from lunar_by_day.days_from_full_moon
    or df.days_from_new_moon is distinct from lunar_by_day.days_from_new_moon
  );

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
    moon_phase_fraction,
    moon_illumination_pct,
    moon_phase_label,
    days_from_full_moon,
    days_from_new_moon,
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
    lunar.moon_phase_fraction,
    lunar.moon_illumination_pct,
    lunar.moon_phase_label,
    lunar.days_from_full_moon,
    lunar.days_from_new_moon,
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
    'rollup-v6',
    now()
  from s
  left join wx w on w.day = s.day
  left join sch_t t on t.day = s.day
  left join sch_c c on c.day = s.day
  left join lateral marts.lunar_context_for_day(s.day) lunar on true
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
    moon_phase_fraction = excluded.moon_phase_fraction,
    moon_illumination_pct = excluded.moon_illumination_pct,
    moon_phase_label = excluded.moon_phase_label,
    days_from_full_moon = excluded.days_from_full_moon,
    days_from_new_moon = excluded.days_from_new_moon,
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

create or replace view marts.user_lunar_patterns as
with symptom_totals as (
  select
    day,
    user_id,
    sum(events)::bigint as symptom_events,
    avg(mean_severity::double precision) as symptom_mean_severity
  from marts.symptom_daily
  group by day, user_id
),
user_days as (
  select user_id, day
  from marts.daily_features
  union
  select user_id, day
  from symptom_totals
),
base as (
  select
    u.user_id,
    u.day,
    coalesce(df.days_from_full_moon, lunar.days_from_full_moon) as days_from_full_moon,
    coalesce(df.days_from_new_moon, lunar.days_from_new_moon) as days_from_new_moon,
    df.hrv_avg::double precision as hrv_avg,
    df.sleep_efficiency::double precision as sleep_efficiency,
    s.symptom_events::double precision as symptom_events,
    s.symptom_mean_severity
  from user_days u
  left join marts.daily_features df
    on df.user_id = u.user_id
   and df.day = u.day
  left join symptom_totals s
    on s.user_id = u.user_id
   and s.day = u.day
  left join lateral marts.lunar_context_for_day(u.day) lunar on true
)
select
  user_id,
  count(*)::bigint as observed_days,
  count(*) filter (where abs(days_from_full_moon) <= 2)::bigint as full_window_days,
  count(*) filter (where abs(days_from_new_moon) <= 2)::bigint as new_window_days,
  count(*) filter (where abs(days_from_full_moon) > 2 and abs(days_from_new_moon) > 2)::bigint as baseline_days,
  count(hrv_avg)::bigint as hrv_observed_days,
  count(hrv_avg) filter (where abs(days_from_full_moon) <= 2)::bigint as hrv_full_days,
  count(hrv_avg) filter (where abs(days_from_new_moon) <= 2)::bigint as hrv_new_days,
  count(hrv_avg) filter (where abs(days_from_full_moon) > 2 and abs(days_from_new_moon) > 2)::bigint as hrv_baseline_days,
  avg(hrv_avg) filter (where abs(days_from_full_moon) <= 2) as hrv_full_avg,
  avg(hrv_avg) filter (where abs(days_from_new_moon) <= 2) as hrv_new_avg,
  avg(hrv_avg) filter (where abs(days_from_full_moon) > 2 and abs(days_from_new_moon) > 2) as hrv_baseline_avg,
  count(sleep_efficiency)::bigint as sleep_observed_days,
  count(sleep_efficiency) filter (where abs(days_from_full_moon) <= 2)::bigint as sleep_full_days,
  count(sleep_efficiency) filter (where abs(days_from_new_moon) <= 2)::bigint as sleep_new_days,
  count(sleep_efficiency) filter (where abs(days_from_full_moon) > 2 and abs(days_from_new_moon) > 2)::bigint as sleep_baseline_days,
  avg(sleep_efficiency) filter (where abs(days_from_full_moon) <= 2) as sleep_full_avg,
  avg(sleep_efficiency) filter (where abs(days_from_new_moon) <= 2) as sleep_new_avg,
  avg(sleep_efficiency) filter (where abs(days_from_full_moon) > 2 and abs(days_from_new_moon) > 2) as sleep_baseline_avg,
  count(symptom_events)::bigint as symptom_observed_days,
  count(symptom_events) filter (where abs(days_from_full_moon) <= 2)::bigint as symptom_full_days,
  count(symptom_events) filter (where abs(days_from_new_moon) <= 2)::bigint as symptom_new_days,
  count(symptom_events) filter (where abs(days_from_full_moon) > 2 and abs(days_from_new_moon) > 2)::bigint as symptom_baseline_days,
  avg(symptom_events) filter (where abs(days_from_full_moon) <= 2) as symptom_events_full_avg,
  avg(symptom_events) filter (where abs(days_from_new_moon) <= 2) as symptom_events_new_avg,
  avg(symptom_events) filter (where abs(days_from_full_moon) > 2 and abs(days_from_new_moon) > 2) as symptom_events_baseline_avg,
  avg(symptom_mean_severity) filter (where abs(days_from_full_moon) <= 2) as symptom_severity_full_avg,
  avg(symptom_mean_severity) filter (where abs(days_from_new_moon) <= 2) as symptom_severity_new_avg,
  avg(symptom_mean_severity) filter (where abs(days_from_full_moon) > 2 and abs(days_from_new_moon) > 2) as symptom_severity_baseline_avg
from base
group by user_id;

commit;
