# Tomsk Extractor Scoring

This document describes the Tomsk harmonic-family protections added in `bots/schumann/tomsk_extractor.py`.

## Summary

The extractor now uses two stages to prevent wrong-family lock-in (for example, `F1≈6.3`):

1. Stage 1 plausibility gate (fast pre-filtering)
2. Stage 2 harmonic family scoring (robust family selection)

If confidence is insufficient, the extractor marks the source as unusable instead of returning misleading frequencies.

## Stage 1: Plausibility Gate

### F2 candidate gating

- The F2 picker now finds local maxima in the smoothed F2 window (instead of only one argmax).
- Candidates are ranked by peak strength (top `N=5`).
- For each candidate, the extractor computes implied `F1 = F2/2`.
- Candidates are rejected when implied `F1` is outside `[7.2, 8.6]` Hz.
- The first candidate that passes plausibility is accepted.

Debug fields:

- `raw.debug.plausibility_reject_f2_count`
- `raw.debug.plausibility_selected_f2_rank`

### Direct F1 sanity check

- Direct F1 picks outside `[7.0, 9.0]` Hz are dropped (`None`) so Stage 2 can decide.

## Stage 2: Harmonic Family Scoring

### Candidate set

Candidate `F1` values are combined from:

1. F1 local maxima in the plausible band `[7.2, 8.6]`
2. Plausible implied F1 values from F2 candidates (`F2/2`)
3. A fallback uniform grid (`0.05` Hz step in `[7.2, 8.6]`) when candidates are sparse

### Scoring model

For each candidate `F1`, expected harmonics are scored at `k*F1` with `k in {1,2,3,4,5}` (when within 40 Hz), using a local max within ±`0.5` Hz on the ridge signal:

- `w1=1.0`
- `w2=1.0`
- `w3=0.8`
- `w4=0.6`
- `w5=0.4`

The best-score candidate is selected as the family root.

### Harmonic refinement

After selecting `best_f1`, each `Fk` is predicted as `k*best_f1` and locally refined within ±`0.6` Hz.

A refined harmonic is accepted only when its local ridge peak exceeds the dynamic threshold for that local band; otherwise it stays `None`.

Debug fields:

- `raw.debug.family_scoring_used`
- `raw.debug.family_best_f1`
- `raw.debug.family_best_score`
- `raw.debug.family_candidate_count`
- `raw.debug.family_top3`

## Fallback and Usability

- If Stage 2 is weak (low family score), the extractor falls back to `repair_harmonics`.
- Fallback is guarded to avoid emitting `F1 < 7.0`.
- `usable` is set to `false` when:
  - `F1` is missing or outside plausible range
  - family score is below threshold
  - or status is not `ok`

This behavior keeps downstream pipelines from preferring low-confidence Tomsk picks.

## Self-test mode

Use:

```bash
python3 bots/schumann/tomsk_extractor.py --self-test --insecure
```

Behavior:

- Fetches one image
- Runs extraction
- Prints `F1/F2` and family debug fields
- Exits `0` when either:
  - `F1` is plausible (`[7.2, 8.6]`), or
  - extraction is explicitly unusable with non-OK status
