begin;

alter table raw.camera_health_checks
  add column if not exists measurement_mode text null,
  add column if not exists hr_status text null,
  add column if not exists hrv_status text null,
  add column if not exists save_scope text not null default 'account',
  add column if not exists debug_meta jsonb null;

update raw.camera_health_checks
set hr_status = case
  when bpm is not null then 'usable'
  else 'not_captured'
end
where hr_status is null;

update raw.camera_health_checks
set hrv_status = case
  when rmssd_ms is not null then 'usable'
  else 'not_captured'
end
where hrv_status is null;

alter table raw.camera_health_checks
  alter column hr_status set default 'not_captured',
  alter column hr_status set not null,
  alter column hrv_status set default 'not_captured',
  alter column hrv_status set not null,
  alter column save_scope set default 'account';

comment on column raw.camera_health_checks.measurement_mode is
  'Capture mode used by the iOS camera quick check (for example quickHR or hrv).';

comment on column raw.camera_health_checks.hr_status is
  'Usability status for heart rate in this run: usable, withheld_low_quality, not_captured, or not_requested.';

comment on column raw.camera_health_checks.hrv_status is
  'Usability status for HRV in this run: usable, withheld_low_quality, not_captured, or not_requested.';

comment on column raw.camera_health_checks.save_scope is
  'Persistence scope recorded for this stored row. Remote rows should remain account.';

comment on column raw.camera_health_checks.debug_meta is
  'Additional camera-check debug metadata such as guidance hints and metric withholding reasons.';

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
  quality_label,
  measurement_mode,
  hr_status,
  hrv_status,
  save_scope
from (
  select
    user_id,
    (ts_utc at time zone 'utc')::date as day,
    ts_utc,
    bpm,
    rmssd_ms,
    sdnn_ms,
    pnn50,
    ln_rmssd,
    stress_index,
    resp_rate_bpm,
    quality_score,
    quality_label,
    measurement_mode,
    hr_status,
    hrv_status,
    save_scope
  from raw.camera_health_checks
) x
order by user_id, day, ts_utc desc;

commit;
