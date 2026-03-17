create schema if not exists marts;

create table if not exists marts.user_daily_features (
  user_id uuid not null,
  day date not null,

  hr_min numeric null,
  hr_max numeric null,
  hrv_avg numeric null,
  steps_total numeric null,
  sleep_total_minutes numeric null,
  sleep_rem_minutes numeric null,
  sleep_core_minutes numeric null,
  sleep_deep_minutes numeric null,
  sleep_awake_minutes numeric null,
  sleep_efficiency numeric null,
  spo2_avg numeric null,
  bp_sys_avg numeric null,
  bp_dia_avg numeric null,

  kp_max numeric null,
  bz_min numeric null,
  sw_speed_avg numeric null,
  flares_count integer null,
  cmes_count integer null,

  sch_fundamental_avg_hz numeric null,
  sch_cumiana_fundamental_avg_hz numeric null,
  sch_any_fundamental_avg_hz numeric null,
  schumann_variability_proxy numeric null,
  schumann_variability_p80 numeric null,

  aqi numeric null,
  pressure numeric null,
  pressure_delta_12h numeric null,
  pressure_delta_24h numeric null,
  temp_delta_24h numeric null,
  humidity numeric null,

  aurora_hp_north_gw numeric null,
  aurora_hp_south_gw numeric null,
  drap_absorption_polar_db numeric null,

  pain numeric null,
  focus numeric null,
  heart numeric null,
  stamina numeric null,
  energy numeric null,
  sleep numeric null,
  mood numeric null,
  health_status numeric null,

  pain_delta integer not null default 0,
  focus_delta integer not null default 0,
  heart_delta integer not null default 0,
  stamina_delta integer not null default 0,
  energy_delta integer not null default 0,
  sleep_delta integer not null default 0,
  mood_delta integer not null default 0,
  health_status_delta integer not null default 0,

  symptom_total_events integer not null default 0,
  symptom_distinct_codes integer not null default 0,
  headache_symptom_events integer not null default 0,
  pain_symptom_events integer not null default 0,
  fatigue_symptom_events integer not null default 0,
  anxiety_symptom_events integer not null default 0,
  poor_sleep_symptom_events integer not null default 0,
  focus_fog_symptom_events integer not null default 0,

  camera_bpm numeric null,
  camera_rmssd_ms numeric null,
  camera_stress_index numeric null,
  camera_quality_score numeric null,
  camera_quality_label text null,

  pressure_drop_exposed boolean null,
  pressure_swing_exposed boolean null,
  aqi_moderate_plus_exposed boolean null,
  aqi_unhealthy_plus_exposed boolean null,
  temp_swing_exposed boolean null,
  kp_g1_plus_exposed boolean null,
  bz_south_exposed boolean null,
  solar_wind_exposed boolean null,
  schumann_exposed boolean null,

  air_quality_sensitive boolean not null default false,
  anxiety_sensitive boolean not null default false,
  geomagnetic_sensitive boolean not null default false,
  pressure_sensitive boolean not null default false,
  sleep_sensitive boolean not null default false,
  temperature_sensitive boolean not null default false,

  migraine_history boolean not null default false,
  chronic_pain boolean not null default false,
  arthritis boolean not null default false,
  fibromyalgia boolean not null default false,
  hypermobility_eds boolean not null default false,
  pots_dysautonomia boolean not null default false,
  mcas_histamine boolean not null default false,
  allergies_sinus boolean not null default false,
  asthma_breathing_sensitive boolean not null default false,
  heart_rhythm_sensitive boolean not null default false,
  autoimmune_condition boolean not null default false,
  nervous_system_dysregulation boolean not null default false,
  insomnia_sleep_disruption boolean not null default false,

  updated_at timestamptz not null default now(),
  primary key (user_id, day)
);

comment on table marts.user_daily_features is
  'Deterministic personal-pattern feature mart built from marts.daily_features plus user-day gauges, symptom totals, local weather, and context flags.';

create index if not exists user_daily_features_day_idx
  on marts.user_daily_features (day desc);

create table if not exists marts.user_daily_outcomes (
  user_id uuid not null,
  day date not null,

  headache_day boolean not null default false,
  pain_flare_day boolean not null default false,
  anxiety_day boolean not null default false,
  poor_sleep_day boolean not null default false,
  fatigue_day boolean not null default false,
  focus_fog_day boolean not null default false,

  hrv_dip_day boolean null,
  high_hr_day boolean null,
  short_sleep_day boolean null,

  headache_events integer not null default 0,
  pain_flare_events integer not null default 0,
  anxiety_events integer not null default 0,
  poor_sleep_events integer not null default 0,
  fatigue_events integer not null default 0,
  focus_fog_events integer not null default 0,
  symptom_total_events integer not null default 0,

  hrv_baseline_median numeric null,
  hr_baseline_median numeric null,
  sleep_baseline_median numeric null,

  updated_at timestamptz not null default now(),
  primary key (user_id, day)
);

comment on table marts.user_daily_outcomes is
  'Daily binary outcomes for the deterministic pattern engine. Outcomes are grouped from self-reported symptoms plus conservative biometric flags.';

create index if not exists user_daily_outcomes_day_idx
  on marts.user_daily_outcomes (day desc);

create table if not exists marts.user_pattern_associations (
  user_id uuid not null,
  signal_key text not null,
  signal_family text null,
  outcome_key text not null,
  outcome_kind text null,
  lag_hours integer not null,
  lag_day_offset integer not null default 0,

  exposure_operator text not null,
  exposure_threshold numeric null,
  exposure_threshold_text text null,

  exposed_n integer not null default 0,
  unexposed_n integer not null default 0,
  exposed_outcome_n integer not null default 0,
  unexposed_outcome_n integer not null default 0,
  exposed_rate numeric not null default 0,
  unexposed_rate numeric not null default 0,
  relative_lift numeric not null default 0,
  odds_ratio numeric not null default 0,
  rate_diff numeric not null default 0,
  observed_weeks integer not null default 0,

  confidence text null,
  confidence_rank smallint not null default 0,
  surfaceable boolean not null default false,

  first_outcome_day date null,
  last_outcome_day date null,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz null,
  updated_at timestamptz not null default now(),

  primary key (user_id, signal_key, outcome_key, lag_hours)
);

comment on table marts.user_pattern_associations is
  'User-specific, explainable signal-to-outcome associations for Pattern Engine v1. Rows are observational and non-diagnostic.';

create index if not exists user_pattern_associations_surface_idx
  on marts.user_pattern_associations (user_id, surfaceable, confidence_rank desc, relative_lift desc, last_seen_at desc);

create or replace view marts.user_pattern_associations_best as
with ranked as (
  select
    a.*,
    row_number() over (
      partition by a.user_id, a.signal_key, a.outcome_key
      order by a.confidence_rank desc, a.relative_lift desc, a.rate_diff desc, a.lag_hours asc
    ) as best_lag_rank
  from marts.user_pattern_associations a
  where a.surfaceable = true
)
select *
from ranked
where best_lag_rank = 1;

comment on view marts.user_pattern_associations_best is
  'Single best lag per user, signal, and outcome following the Pattern Engine v1 tie-break rules.';

alter table marts.user_daily_features enable row level security;
alter table marts.user_daily_outcomes enable row level security;
alter table marts.user_pattern_associations enable row level security;

drop policy if exists "user_daily_features_select_own" on marts.user_daily_features;
create policy "user_daily_features_select_own"
  on marts.user_daily_features for select
  using (auth.uid() = user_id);

drop policy if exists "user_daily_outcomes_select_own" on marts.user_daily_outcomes;
create policy "user_daily_outcomes_select_own"
  on marts.user_daily_outcomes for select
  using (auth.uid() = user_id);

drop policy if exists "user_pattern_associations_select_own" on marts.user_pattern_associations;
create policy "user_pattern_associations_select_own"
  on marts.user_pattern_associations for select
  using (auth.uid() = user_id);
