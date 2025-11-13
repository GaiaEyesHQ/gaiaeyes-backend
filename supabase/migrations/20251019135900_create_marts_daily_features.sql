-- Ensure marts.daily_features exists before dependent symptom-space analytics.
create schema if not exists marts;

do $$
begin
  if not exists (
    select 1
    from information_schema.tables
    where table_schema = 'marts'
      and table_name   = 'daily_features'
  ) then
    execute $ddl$
      create table marts.daily_features (
        user_id uuid not null,
        day date not null,
        hr_min numeric,
        hr_max numeric,
        hrv_avg numeric,
        steps_total numeric,
        sleep_total_minutes numeric,
        sleep_rem_minutes numeric,
        sleep_core_minutes numeric,
        sleep_deep_minutes numeric,
        sleep_awake_minutes numeric,
        sleep_efficiency numeric,
        spo2_avg numeric,
        bp_sys_avg numeric,
        bp_dia_avg numeric,
        kp_max numeric,
        bz_min numeric,
        sw_speed_avg numeric,
        src text default 'rollup-v1',
        updated_at timestamptz not null default now(),
        flares_count integer,
        cmes_count integer,
        schumann_station text,
        sch_fundamental_avg_hz numeric,
        sch_f1_avg_hz numeric,
        sch_f2_avg_hz numeric,
        sch_f3_avg_hz numeric,
        sch_f4_avg_hz numeric,
        sch_f5_avg_hz numeric,
        sch_cumiana_station text,
        sch_cumiana_fundamental_avg_hz numeric,
        sch_cumiana_f1_avg_hz numeric,
        sch_cumiana_f2_avg_hz numeric,
        sch_cumiana_f3_avg_hz numeric,
        sch_cumiana_f4_avg_hz numeric,
        sch_cumiana_f5_avg_hz numeric,
        sch_any_fundamental_avg_hz numeric,
        sch_any_f1_avg_hz numeric,
        sch_any_f2_avg_hz numeric,
        sch_any_f3_avg_hz numeric,
        sch_any_f4_avg_hz numeric,
        sch_any_f5_avg_hz numeric,
        constraint daily_features_pkey primary key (user_id, day)
      );
    $ddl$;
  end if;
end$$;

create index if not exists idx_daily_features_user_day
    on marts.daily_features (user_id, day);
