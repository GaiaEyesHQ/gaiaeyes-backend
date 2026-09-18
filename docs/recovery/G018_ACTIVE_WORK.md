# G018 — music-only EarthScope reels

September 16, 2026 UTC / September 15 America/Chicago. **Review-ready local source change; coordinator review pending.** Jennifer selected background music only for current Gaia social reels and deferred voiceover until she reopens it. The coordinator relayed this direction while recording D038. G017 Android work remains review-ready and unchanged.

Evidence packet: `/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g018-music-only-reels/`.

## Result

The daily EarthScope reel workflow now explicitly selects `REEL_VOICE_ENABLED: "0"`. In this mode the builder skips narration text preparation and all primary/fallback TTS calls, even when `OPENAI_API_KEY` is present. It deletes the previous scratch `vo.wav`, passes no narration to the muxer, and does not probe or stretch the visual sequence for old narration.

The existing workflow supplied `REEL_BED_URL` for `social/earthscope/music/bed01.wav`, but the builder ignored that variable and the workflow's `--bed-url` argument because it has no argument parser. The builder now honors that existing URL directly. The workflow uses its already-supported environment output path and stops passing ignored arguments. If no explicit bed URL is supplied, existing manifest/mood selection still works. Missing/empty music in music-only mode stops the build before producing a silent output or reusing stale music.

The music-only branch retains looping, configured gain, a short fade and AAC muxing. The visual hook, story cards, stats card, captions and writer code are unchanged. Without a separate duration override, the existing four-card sequence remains 12.950 seconds; no new pacing or readability claim is inferred from the fake audio tests.

Optional narration remains implemented. Other callers default to `REEL_VOICE_ENABLED=1`, preserving the primary/fallback TTS flow, optional/required VO behavior, ducking and voice-duration extension. `REEL_REQUIRE_VO=1` with voice disabled is a configuration conflict that fails before work. The daily workflow keeps `REEL_REQUIRE_VO=0`. The upstream `generate` job retains its writer API key; no key or account was changed.

## Scoped diff

| File | Change |
|---|---|
| `bots/earthscope_post/reel_builder.py` | Explicit voice switch; skip narration block; clear scratch audio; honor existing direct bed URL; retain manifest selection and enabled narration; reject missing/empty music-only audio |
| `.github/workflows/gaia_eyes_daily.yml` | Select voice disabled in the reel job, log that mode, remove ignored CLI arguments. Preserve existing bed URL, output env, writer key and publication steps |
| `tests/bots/test_earthscope_reel_audio.py` | Fifteen fake/no-network cases covering actual main orchestration and generated mux command |
| `docs/recovery/G018_ACTIVE_WORK.md` | This handoff and rollout boundary |

Targets were clean before editing. The coordinator assigned this sole Gaia writer; no competing target edits were found. Existing dirty Android/recovery/social work was checkpointed and preserved. No other task or agent was started.

## Verification

Commands run from the repository:

```sh
venv/bin/python -m pytest tests/bots/test_earthscope_reel_audio.py tests/bots/test_earthscope_reel_builder.py -q
venv/bin/python -m py_compile bots/earthscope_post/reel_builder.py tests/bots/test_earthscope_reel_audio.py
git diff --check
```

**35 tests passed**: fifteen new audio/configuration cases and twenty existing renderer/story/card cases. Python compilation and diff validation passed. Final log/XML: `pytest-focused-final.log` and `pytest-focused-final.xml`. The initial 34-pass/one-failure run is retained; that test looked for the writer key in `render` instead of its actual `generate` job and was corrected.

The tests verify:

- Disabled mode with a present synthetic key makes no TTS, narration-resolution or narration-duration call; stale voice is removed and excluded from the mux command.
- The existing explicit bed takes precedence without a manifest fetch; manifest selection still supports mood and both `url`/`file` entries when no override is supplied.
- Music-only output loops the bed, applies the existing gain/fade, maps only video/music and encodes AAC. Failed/empty bed downloads cannot reuse stale audio or produce a silent result.
- Enabled narration retains primary success, fallback success, optional failure, required failure, missing-key behavior, ducking and duration extension.
- The workflow selects disabled narration and preserves the upstream writer key. Default narration behavior for other callers remains available.

HTTP, ffmpeg and media probes were faked in the new tests; no live project API, storage asset, TTS, database or media publication call was made. No actual MP4 was rendered or listened to in this source increment. Existing renderer tests exercised their usual image/layout checks; this is not a new end-to-end reel acceptance.

The Supabase skill was used only to check the existing public-asset URL convention. Public documentation was fetched, with the changelog and storage guide retained in the packet. No relevant public-download breaking change was identified. The [official storage guide](https://supabase.com/docs/guides/storage/serving/downloads) documents the existing public URL format; no bucket, policy, schema or storage configuration was changed. The explicit fake-test scope governs verification here; no live database test was run.

## Exact rollout boundary

This change is local and unstaged. **No commit/push, workflow dispatch/retry, scheduled job edit in the live service, social posting, credential/account change or deployment occurred.** Existing remote workflows and published reels are unaffected until a separately approved rollout lands this source on the branch used by the scheduled workflow.

Coordinator review should inspect the three-file implementation/test diff and retained results. Before any publishing run, the next separately authorized acceptance should use the existing selected bed and a non-publishing render, verify an audio stream and readable unchanged cards, listen for music with no narration, and confirm logs contain the explicit disabled mode with no TTS attempt. This checkpoint does not authorize running the full daily workflow as a preview: it contains storage upload and social publication steps.

Once reviewed and separately authorized, land the source/workflow change through the normal rollout path. Narration should remain disabled unless Jennifer reopens that direction; re-enabling is an explicit configuration/product choice, not a failure fallback. No new start approval is needed for this completed source increment; deployment/publication remains outside it.

G017's 31-artifact packet, its six source/handoff hashes and the subsequent account-state correction are retained. The preceding Gaia report is copied as `preceding-g017-report.json`; G018 has its own fresh report. Root continues to own portfolio decisions, the human queue and final acceptance.
