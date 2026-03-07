begin;

-- 2.1 Raw camera health checks (per measurement event)
create table if not exists raw.camera_health_checks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  ts_utc timestamptz not null default now(),

  source text not null default 'ios_camera',
  duration_sec int not null,
  fps int null,

  bpm numeric null,

  -- HRV time-domain (milliseconds)
  avnn_ms numeric null,
  sdnn_ms numeric null,
  rmssd_ms numeric null,
  pnn50 numeric null,
  ln_rmssd numeric null,

  -- "strain" index (Baevsky stress index) from IBI distribution
  stress_index numeric null,

  -- respiration estimate (breathing rate) from IBI/PPG modulation (very noisy)
  resp_rate_bpm numeric null,

  -- Signal quality
  quality_score numeric not null default 0, -- 0..1
  quality_label text not null default 'unknown', -- good|ok|poor|unknown
  artifacts jsonb null, -- e.g. dropped_frames, motion_score, saturation_hits

  -- Raw series (compact)
  ibi_ms jsonb null,        -- array of IBIs in ms
  ibi_ts_ms jsonb null,     -- optional timestamps aligned to capture start (ms)
  ppg_ds jsonb null,        -- downsampled PPG values (optional)
  ppg_ds_hz numeric null,   -- downsampled rate

  created_at timestamptz not null default now()
);

comment on table raw.camera_health_checks is
  'Camera/flash PPG health check events (exploratory). Stores BPM, HRV time-domain metrics, quality, and optional raw series.';

create index if not exists camera_health_checks_user_ts_idx
  on raw.camera_health_checks (user_id, ts_utc desc);

-- 2.2 Daily rollup view (latest check per day, per user)
create or replace view marts.camera_health_daily as
select distinct on (user_id, day)
  user_id,
  day,
  ts_utc as latest_ts_utc,
  bpm,
  rmssd_ms,
  sdnn_ms,
  pnn50,
  ln_rmssd,
  stress_index,
  resp_rate_bpm,
  quality_score,
  quality_label
from (
  select
    user_id,
    (ts_utc at time zone 'utc')::date as day,
    ts_utc, bpm, rmssd_ms, sdnn_ms, pnn50, ln_rmssd, stress_index, resp_rate_bpm, quality_score, quality_label
  from raw.camera_health_checks
) x
order by user_id, day, ts_utc desc;

-- 2.3 RLS
alter table raw.camera_health_checks enable row level security;

drop policy if exists "camera_health_checks_select_own" on raw.camera_health_checks;
create policy "camera_health_checks_select_own"
  on raw.camera_health_checks for select
  using (auth.uid() = user_id);

drop policy if exists "camera_health_checks_insert_own" on raw.camera_health_checks;
create policy "camera_health_checks_insert_own"
  on raw.camera_health_checks for insert
  with check (auth.uid() = user_id);

drop policy if exists "camera_health_checks_delete_own" on raw.camera_health_checks;
create policy "camera_health_checks_delete_own"
  on raw.camera_health_checks for delete
  using (auth.uid() = user_id);

commit;
