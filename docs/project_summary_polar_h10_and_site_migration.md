# Gaia Eyes — Backend/App/WordPress + Polar H10 Streaming Summary

**Purpose:** Working doc for future sessions (human + Codex) so no one re‑opens solved loops. Place this in `/docs/` and skim it **before** making changes.

**Period covered:** ~2 months of fixes culminating in Polar H10 ECG + HR streaming and stable app/backend sync.

---

## TL;DR Outcomes

- **Space visuals**: migrated to Supabase; `/v1/space/visuals` emits **`/drap,/nasa,/aurora`** paths; cdn_base set; WordPress uses GAIA_MEDIA_BASE.
- **Features / SpO₂**: `spo2_avg` added to `/v1/features/today` (mart **select**, normalization, payload, diag). iOS model tolerant; formatter fixed; card displays again.
- **WordPress**: plugins made API‑first; visuals now use Supabase cdn_base; detail cards tolerant to backend shape; baseline fallback to avoid “card vanished.”
- **Unified auth (design ready)**: dependency auth with public-read allowlist + Bearer tokens (READ/WRITE). Can be rolled out later.
- **iOS dashboards**: type-check perf fixes, local view cleanup; Live HR optional badge; debounced upload-triggered refresh (15s).
- **BLE / Polar H10**: **HR streaming + ECG** working. Error 9 (invalid state) resolved via feature enabling, capability/contact gating, settle delay, bounded probe, and Rx+async continuation fix.

---

## Backend (FastAPI + Supabase)

### A. Space Visuals / Supabase
- Standardized uploader: buckets now under `space-visuals` with subpaths `/drap`, `/nasa`, `/aurora`, `/magnetosphere`, `/space`.
- `/v1/space/visuals` returns **relative** asset paths + `cdn_base` (Supabase public URL), unified `items`, and a baseline if few assets are found.
- WordPress visuals plugin updated to accept `items` (not just `images`), map new keys (`aia_304`, `lasco_c2`, `drap`, `ccor1`), and render even when legacy JSON is missing.
- **Reminder** tasks:
  - Ensure endpoint emits `/drap,/nasa,/aurora` (not `/images/space`).
  - If legacy paths exist in DB: run migration to rewrite `ext.space_visuals.image_path` accordingly.

### B. Space forecast (outlook) normalization
- Route: `/v1/space/forecast/outlook` made to emit stable keys:
  - `headline`, `confidence`, `alerts`,
  - `impacts: { gps, comms, grids, aurora }`,
  - `flares: { max_24h, total_24h, bands_24h }`,
  - `cmes: { headline, stats: { total_72h, earth_directed_count, max_speed_kms } }`.
- WordPress is tolerant now, but server‑side normalization is preferred.

### C. Features / SpO₂
- Added `spo2_avg` to mart **SELECT** lists and float coercion. Normalize 0–1 → 0–100; clamp >100.
- `/v1/diag/features` includes `spo2_avg` in **cache** + **mart** snapshots.
- iOS: `FeaturesToday` reads top-level `spo2_avg` and nested `health.spo2_avg`; `spo2AvgDisplay` normalizes; card formats percent safely.

### D. CI / GH Actions
- Space visuals action: Supabase-only upload + smoke check; remove GitHub media pushes entirely.
- Add smoke checks:
  - `/v1/space/visuals/diag` → `cdn_base != null`
  - `/v1/space/visuals` → `items.length >= 5`

---

## WordPress

- Visuals plugin now API‑first; uses `cdn_base || GAIA_MEDIA_BASE`; merges `items ∪ images`; baseline when APIs fail.
- Space Weather Detail plugin: API‑first for `features/today` + `forecast/outlook`; tolerant mapping (kp/bz/sw/flares/cmes/impacts/confidence); added safety fallback to avoid blank cards.
- Config: in `wp-config.php` set:
  ```php
  define('GAIA_MEDIA_BASE', 'https://<supabase>/storage/v1/object/public/space-visuals');
  define('GAIAEYES_API_BASE', 'https://gaiaeyes-backend.onrender.com');
  // optional while auth stabilizes:
  define('GAIAEYES_API_BEARER', '<read-token>');
  ```

---

## iOS App

### A. Performance / UI stability
- Split large `SpaceWeatherCard(...)` expression into a two-step build to avoid compiler timeouts.
- Moved local view structs to file scope (e.g., LiveHRBadge) to fix “private in local scope” errors.
- Added a small “Manage” button on the BLE card so Scan/Connect is accessible while connected.
- Debounced “upload-triggered features refresh” to **15s**, with readable skip logs.

### B. Features / SpO₂
- `FeaturesToday` now tolerates: `spo2_avg`, `health.spo2_avg`, `spo2_avg_pct`, `spo2_mean`.
- `spo2AvgDisplay` normalizes fraction→percent, clamps, and filters junk values.
- HealthStatsCard uses a formatter that accepts 0–1 or 0–100.

---

## BLE / Polar H10 — What finally worked

**Symptoms we addressed:**
- Error 9 (invalid state) on `requestStreamSettings` or `startEcgStreaming`,
- Error 8 when querying capabilities,
- Occasional EXC_BAD_ACCESS in ECG start (Swift concurrency + Rx race),
- Infinite “ECG probe” loops and “Not connected” flips.

**Key fixes (layer by layer):**

1) **Disable races with CoreBluetooth GATT HR**
   - Paused CB HR connection before ECG start and disabled auto-reconnect during ECG.
   - Added a **settle delay** (~1.0s) before requesting settings.

2) **Enable Polar SDK features at init**
   - Polar API created with feature set (**HR** + **Online Streaming**; also **features configuration** + **device info** when needed).
   - This allows `getAvailableOnlineStreamDataTypes` and HR streaming to work without error 8/9.

3) **Use Online Streaming API for HR/contact**
   - Switched from deprecated `deviceHrObserver` to **`startHrStreaming()`**.
   - Stream updates **contact** and HR in near real-time.

4) **Capability & contact gating**
   - On connect: proactively query `getAvailableOnlineStreamDataTypes(id)`; cache `supportedStreams`.
   - ECG start: if `.ecg` not yet advertised **but** online streaming ready → **attempt settings anyway** (don’t hard-abort).
   - If contact supported and `OFF`, wait up to 5s for `ON` before attempting.

5) **Bounded ECG feature probe**
   - Probe waits for `.ecg` (max 10s), then attempts `requestStreamSettings` up to **3** times; backs off **0.7s** on error 9; aborts cleanly; cancels on disconnect.

6) **Rx + Swift Concurrency interop fix (critical)**
   - In `PolarECGSession.startStreaming(settings:)`:
     - **Create the Rx subscription first**, then **immediately resume** the `withCheckedThrowingContinuation` with the `Disposable`.
     - Do **not** resume continuation from `onNext/onError/onCompleted` to avoid double‑resume / race → **EXC_BAD_ACCESS**.
   - Keep the `Disposable` strongly referenced; stop stream on `onError/onCompleted`.

7) **UX polish**
   - “Manage” button on BLE card for Scan/Connect while connected.
   - Debounced upload-triggered refresh to stop 2s spam while streaming.

**Result:** HR stream shows contact **ON**; ECG uploads flow and backend accepts; app refreshes features sanely (debounced).

---

## What not to do (aka pitfalls we hit)

- **Don’t** gate feature refresh on a stale `backend DB=false` flag; verify `/health` fresh before deciding to skip.
- **Don’t** rely on legacy GitHub JSON for visuals; use `/v1/space/visuals` + `cdn_base` + Supabase buckets.
- **Don’t** resume `withCheckedThrowingContinuation` inside Rx closures; resume immediately after creating the subscription (return the `Disposable`), and only log/stop in closures.
- **Don’t** expect Polar SDK to advertise `.ecg` without enabling the correct feature set at init. Enum case names vary by version—use autocomplete (e.g., `.feature_hr`, `.feature_polar_online_streaming`).
- **Don’t** automatically disconnect SDK on first ECG start failure; retry once with a short backoff, and only then consider reconnect.

---

## Playbooks

### A. Space visuals sanity
- `GET /v1/space/visuals/diag` → check `cdn_base != null`
- `GET /v1/space/visuals` → `items.length >= 5` and relative URLs under `/drap|/nasa|/aurora|/magnetosphere|/space`.
- WP page source: look for `ge-space-debug base=… images=N videos=M` comment.

### B. Features / SpO₂ sanity
- `GET /v1/diag/features` → `metrics.spo2_avg` non-null (cache + mart)
- `GET /v1/features/today` → payload includes `spo2_avg` (90..100) or normalized fraction
- iOS: `current.spo2AvgDisplay` non-nil and card formatter shows `XX%`

### C. Polar H10 ECG start
1) Ensure Polar API init features include HR + Online Streaming (and config/device info if SDK requires).
2) Pause CB HR; wait ~1s.
3) Start HR streaming via SDK (`startHrStreaming`) to get contact; contact `ON` if supported.
4) Query `getAvailableOnlineStreamDataTypes`; if `.ecg` missing but streaming is ready, try anyway.
5) `requestStreamSettings(id, .ecg)` → `startEcgStreaming(id, settings)`; keep `Disposable`; continuation resume fix.
6) On error 9 → single backoff retry; if still failing, consider SDK reconnect fallback (not always needed).

---

## Open items / Nice to haves

- Add **SDK reconnect fallback** only if error 9 persists after one retry + settle.
- Optional: show **Contact: ON/OFF** + capability chips beside ECG Start button.
- Finish unified auth rollout (public-read → Bearer) once WP sends tokens everywhere.
- Add a CI check that forbids re‑introducing `images/space/` in DB or plugins.

---

## Appendix: quick code anchors (for future edits)

- Backend visuals: `app/routers/space_visuals.py`
- Outlook: `app/routers/space_forecast.py`
- Features: `app/routers/features.py`, `app/routers/summary.py`
- WP Visuals: `wp-content/mu-plugins/gaiaeyes-space-visuals.php`
- WP Space Weather Detail: `wp-content/mu-plugins/gaiaeyes-space-weather-detail.php`
- iOS Features: `ios/GaiaExporter/FeaturesModels.swift`
- iOS Views: `ios/GaiaExporter/Views/ContentView.swift`
- iOS AppState: `ios/GaiaExporter/ViewModels/AppState.swift`
- BLE Manager: `ios/GaiaExporter/Views/BleManager.swift`
- HR Session: `ios/GaiaExporter/Views/HrSession.swift`
- Polar Manager: `ios/GaiaExporter/Services/Polar/PolarManager.swift`
- Polar ECG Session: `ios/GaiaExporter/Services/Polar/PolarECGSession.swift`

---

**Author’s note:** If a future change re‑introduces Polar error 9 or the EXC_BAD_ACCESS crash, check **Polar API feature flags** at init and the **continuation body** in `PolarECGSession.startStreaming(settings:)` first—those were the critical levers.
