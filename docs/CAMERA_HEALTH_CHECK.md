# Camera Health Check (iOS PPG)

This feature adds a camera/flash based "Quick Health Check" in the iOS app for exploratory wellness context.

Safety language in app UI:
- "Estimates for wellness context only. Not medical advice."
- No arrhythmia detection claims.

## What ships

- Home dashboard CTA: `Quick Check` button.
- Camera measurement flow:
  - Warm-up: 3 seconds (discarded)
  - Record: 30-45 seconds
  - Early stop when quality is good and enough beats are collected
- Result screen shows:
  - live signal quality (`Weak`, `Improving`, `Good`, `Excellent`) during capture
  - live guidance before the run completes (for example lens coverage, pressure, stillness)
  - BPM when usable
  - RMSSD when HRV quality passes
  - Optional SDNN, pNN50, AVNN, lnRMSSD for successful HRV runs
  - explicit partial state when HR is usable but HRV is withheld
  - explicit poor state with one short reason and a retry checklist
- Save behavior:
  - local copy is stored for completed runs
  - signed-in users sync to account when remote save succeeds
  - result UI states whether the run was saved to account, saved locally only, or not saved
- One-tap rerun with preserved guidance hints after poor runs.
- Optional developer toggle for "Copy Debug JSON."

## Supabase schema

Migration file:
- `supabase/migrations/20260307113000_create_camera_health_checks.sql`
- `supabase/migrations/20260308020500_grant_camera_health_schema_access.sql`
- `supabase/migrations/20260318103000_expand_camera_health_check_statuses.sql`

Objects added:
- `raw.camera_health_checks` table
- `marts.camera_health_daily` view (latest check per user/day)
- RLS policies for own-row select/insert/delete
- Grants for `authenticated` role to use `raw`/`marts` schemas and query camera-health objects

Additional stored fields:
- `measurement_mode`
- `hr_status`
- `hrv_status`
- `save_scope`
- `debug_meta`

Common troubleshooting:
- If the app shows:
  - `Supabase error 403`
  - `{"code":"42501","message":"permission denied for schema raw"}`
- Then the grants migration above has not been applied in the target Supabase project.

## iOS direct Supabase writes

The app writes directly to Supabase PostgREST using authenticated session headers:
- `Authorization: Bearer <supabase_access_token>`
- `apikey: <SUPABASE_ANON_KEY>`
- `Content-Profile: raw` for inserts
- `Accept-Profile: marts` for daily view reads

Relevant files:
- `gaiaeyes-ios/ios/GaiaExporter/Services/Camera/CameraHealthSupabaseClient.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/Auth/AuthManager.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Views/Camera/CameraHealthCheckView.swift`

Auth details:
- `AuthManager.validAccessToken()` refreshes token before use
- `AuthManager.currentSupabaseUserId()` decodes JWT `sub` and is written as `user_id`

## PPG processing pipeline (Swift)

Implemented in:
- `gaiaeyes-ios/ios/GaiaExporter/Services/Camera/CameraPPGProcessor.swift`
- `gaiaeyes-ios/ios/GaiaExporter/Services/Camera/PPGSignalQuality.swift`

Pipeline:
1. Green-channel mean from center ROI each frame.
2. Downsample/resample target around 30 Hz.
3. DC removal via rolling mean (~1 second window).
4. Bandpass with IIR biquads (0.7-3.5 Hz).
5. Adaptive peak detection + minimum peak spacing.
6. IBI computation and artifact rejection:
   - hard bounds: 300-2000 ms
   - median/MAD outlier gate
7. Quality scoring (0-1):
   - valid IBI ratio
   - SNR proxy
   - IBI stability
   - saturation/motion/dropped-frame penalties
8. Metrics:
   - BPM (if stable)
   - AVNN, SDNN, RMSSD, pNN50, lnRMSSD (quality-gated)
   - Baevsky stress index (quality-gated)
   - Respiration estimate only when confidence is adequate

Quality gate for HRV persistence:
- `quality_score >= 0.58`
- `quality_label in ('good', 'ok')`
- Sufficient valid beats

Partial result behavior:
- HR can still be surfaced and saved when HRV is withheld.
- HRV can be marked `withheld_low_quality` without turning the whole run into a failure.
- Latest-check cards use overall states:
  - `Good`
  - `Partial`
  - `Poor`
  - `Pending`

## Dashboard integration

Home integration:
- `Quick Check` button opens camera check sheet.
- "Latest Check" card shows latest camera summary with overall status, available metrics only, and save scope.
- Card reads `marts.camera_health_daily` directly from iOS via Supabase.

Health & Symptoms integration:
- Latest Quick Health Check card labels runs as `Good`, `Partial`, `Poor`, or `Pending`.
- Partial summaries show HR when available and hide unavailable HRV instead of placeholder values.
- Local-only saves can still appear through iOS local fallback storage.

Relevant file:
- `gaiaeyes-ios/ios/GaiaExporter/Views/ContentView.swift`

## Health status scorer integration

Backend change in:
- `bots/gauges/gauge_scorer.py`

Logic:
- Primary HRV source remains `marts.daily_features.hrv_avg`.
- Fallback source adds camera daily HRV when quality is acceptable.
- Uses camera RMSSD when available, otherwise infers RMSSD from `ln_rmssd`.
- Optional mild stress-index penalty is applied only when camera quality gating passes.

## iOS permissions

`Info.plist` now includes:
- `NSCameraUsageDescription`

Torch uses camera hardware and does not require extra permission key.

## Reviewer verification

1. Run a measurement on device:
   - good still finger case
   - moving finger case
   - partial cover case
2. Confirm insert rows:
```sql
select ts_utc, bpm, rmssd_ms, sdnn_ms, pnn50, ln_rmssd, stress_index, quality_score, quality_label,
       measurement_mode, hr_status, hrv_status, save_scope
from raw.camera_health_checks
where user_id = '<your_user_id>'
order by ts_utc desc
limit 10;
```
3. Confirm daily view:
```sql
select *
from marts.camera_health_daily
where user_id = '<your_user_id>'
order by day desc
limit 14;
```
4. Confirm home dashboard card updates after save.
5. Confirm a signed-out run shows `Saved locally only` and still appears on-device.
