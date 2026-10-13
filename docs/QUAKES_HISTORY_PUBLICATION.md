# Quake history publication and comparison recovery

`quakes-history.yml` generates the existing USGS daily/monthly JSON contract and
publishes `space-visuals/data/quakes_history.json` through
`scripts/sync_quakes_history.py publish`. Success requires valid, fresh quake
series, a successful upload, and matching JSON from an anonymous public read-back.
It does not use the image-only space visuals uploader.

On successful completion on `main`, `compare-series.yml` fetches that public
object, builds space history and the comparison, and commits all three JSON files
together to `GaiaEyesHQ/gaiaeyes-media` main. Manual dispatch remains available for
recovery. The previous independent 05:20 schedule is replaced by completion
ordering so a slow or failed history publication cannot silently reuse an old
media checkout. There is no fallback to stale media quake data.

History and Compare share the `quakes-history-publication` concurrency group,
including manual runs, with running jobs never cancelled by a newer run. This
serializes these workflows' writes to the mutable Storage source and their media
publication. If multiple history runs are queued, Compare consumes the latest
verified public history when it starts. This is not a cross-service transaction;
Storage can be newer than media between workflow runs or after a Compare failure.

Both source generation timestamps must be at most 48 hours old. Each required
daily series must reach at least the UTC date two days ago. Quake history also
needs a recent **nonzero** `all_daily` bin: the generator pads through today, so a
current zero-filled endpoint alone does not prove recent USGS observations.
These bounds allow the daily schedule and UTC day boundaries. Invalid or stale
inputs fail before replacing the prior local comparison; a failed build cannot
reach the media commit step. Optional M4+ behavior and existing output keys,
labels, daily/monthly series remain unchanged. Comparison timestamps now carry
an explicit UTC `Z`. Both established monthly arrays (`m5p_monthly`,
`m6p_monthly`) are required and checked for valid, ordered month/count pairs and a
recent endpoint. Optional M4+ daily/monthly arrays receive the corresponding
validation if present; their absence is allowed.

The USGS generator queries contiguous, timezone-qualified UTC windows no longer
than 30 days, ending at a single cutoff captured when the build starts. USGS query
bounds are inclusive, so the generator counts each chunk as `[start, end)` to
assign a shared-boundary event only to the following chunk. There are no skipped
calendar days between chunks. The final window includes events from the current
UTC day before that cutoff. Today's day/month totals are **partial**, not
full-day/full-month observations; the existing `meta.note` records this cutoff.
An event exactly at the final cutoff is excluded until a later build. The build
timestamp remains the generation completion time, which may be later than the
cutoff. The existing output structure is unchanged. See the
[USGS time-boundary contract](https://earthquake.usgs.gov/fdsnws/event/1/#parameters).

Media publication uses `scripts/publish_compare_series.sh`. It commits only the
three generated files, fetches and rebases onto media `main`, and stops immediately
on a rebase conflict. Non-fast-forward pushes retry at most three times, with a
fresh successful rebase required before each attempt. Success additionally
requires the published commit to be reachable from fetched remote `main` and the
remote blob hashes for all three files to match the intended generated files.
Unrelated media commits are retained. Push exit status alone is not acceptance.

## Owner-controlled rollout

Do not merge or dispatch production workflows until the release owner approves
the tested commit. No production dispatch is needed to test this change.

1. Review the draft PR and its regression/YAML checks, then merge the approved
   commit. Supabase automatic migrations remain disabled; no schema, permission,
   credential, or hosting changes are needed.
2. Dispatch `quakes-history.yml` on the merged `main` (or wait for its daily
   05:15 UTC schedule). Record the run URL, commit, and UTC start time. Require
   the upload step's `publish verified` log, generation timestamp, and
   `newest_quake_day`. Read the anonymous Storage object and verify its timestamp
   is from this run and its newest nonzero quake day is within two UTC days.
3. Watch the automatically chained `compare-series.yml` run. It must start after
   successful publication, log the same quake source timestamp/newest day, build
   current space history, and log `published commit=... verified_files=3` after
   verifying the pushed media commit and contents. Do not launch a
   duplicate comparison while the chained run is active. If necessary after a
   failure, dispatch only Compare once Storage has been verified.
4. Read the public media `data/quakes_history.json` and
   `data/compare_series.json` from `main` with a cache-busting query. Require the
   media quake JSON to match the Storage JSON, and all quake arrays in Compare
   to match that history (M4+ remains optional). Require Compare's generation
   timestamp to be at or after the verified history build, and inspect latest
   daily points **and the newest nonzero earthquake day**. A fresh build timestamp
   alone is not acceptance. Also validate space history's daily endpoints.
5. After CDN/WordPress caches expire, have an authenticated site owner check
   Compare's plotted dates. Anonymous inspection returned HTTP 403 during the
   diagnosis, so visible page impact is unverified. The separate DB-backed
   `/v1/quakes/history` used by earthquake detail is unaffected.

Public media URLs:

- https://raw.githubusercontent.com/GaiaEyesHQ/gaiaeyes-media/main/data/quakes_history.json
- https://raw.githubusercontent.com/GaiaEyesHQ/gaiaeyes-media/main/data/compare_series.json

Storage URL: `${SUPABASE_URL}/storage/v1/object/public/space-visuals/data/quakes_history.json`.
Read-back and consumer download are anonymous. The publisher reuses the existing
server-side Storage helper and credentials; the consumer needs only the project
URL. Public CDN propagation/mismatch, unavailable Storage, and stale inputs now
fail visibly. If Storage publishes but Compare fails, the prior media commit
remains in place when failure occurs before the media push; fix the reported
failure and retry Compare. A post-push verification failure can mean that remote
main advanced again; inspect its commit and all three files before retrying.
The two destinations are ordered, not an atomic cross-service transaction.

## Local verification

```sh
python -m pytest -q tests/scripts/test_quakes_history_publication.py \
  tests/scripts/test_compare_publication.py
yamllint .github/workflows/quakes-history.yml \
  .github/workflows/compare-series.yml \
  .github/workflows/quakes-history-tests.yml
bash -n scripts/publish_compare_series.sh
git diff --check
```

Tests mock all network traffic and cover missing/malformed JSON, rejected Storage
writes, unavailable/invalid/mismatched anonymous read-back, stale source timestamps
and series, misleading zero-filled endpoints, preservation of existing comparison
output on failure, monthly/optional M4+ validation, generator compatibility, and
workflow ordering/publication. Boundary fixtures cover the full 730-day window,
events immediately before/at/after chunk transitions, the current-day cutoff,
exact midnight, and a run that finishes the following day. Local bare Git remotes
exercise overlapping pushes, conflicts, bounded retries, preservation of unrelated
commits, and detection of absent commits or changed content after a successful
push exit. Tests never contact production.

Read-only diagnosis on October 13, 2026: media history timestamp was
`2025-11-26T05:34:48Z`; Compare timestamp was `2026-10-13T12:47:21` but its quake
series still ended `2025-11-26`. Space history timestamp was
`2026-10-13T12:47:21Z` with all three required daily series reaching `2026-10-13`.
The new validator rejected the stale quake source and accepted that space source.
