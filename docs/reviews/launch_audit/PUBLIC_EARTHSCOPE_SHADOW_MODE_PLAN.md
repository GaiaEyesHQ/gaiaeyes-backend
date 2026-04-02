# Public EarthScope Shadow Mode Plan

This plan defines how to evaluate public EarthScope writer changes without risking live posting quality.

## Goal

Create a non-publishing review path for candidate public-writer output.

Shadow mode should answer:

- what the live writer would publish today
- what the candidate writer would publish today
- whether the candidate sounds better
- whether the candidate preserves the same facts and field structure

## Primary Rule

Shadow mode should not create a new permanent parallel content source unless explicitly approved.

Preferred outputs:

- GitHub Actions artifacts
- local review JSON
- optional issue comment or summary log

Avoid for the first pass:

- new Supabase table
- new production content path
- new posting branch in the workflow

## Scope

Shadow mode should compare:

- `title`
- `caption`
- `hashtags`
- `body_markdown`
- `metrics_json.sections.caption`
- `metrics_json.sections.snapshot`
- `metrics_json.sections.affects`
- `metrics_json.sections.playbook`

It should also record:

- prompt variant or writer mode used
- model resolved at runtime
- whether rewrite fallback was used
- whether similarity guard or rescue hooks fired

## Recommended Output Format

One JSON review bundle per run.

Suggested path:

- `tmp/earthscope_shadow/<day>-<platform>.json` locally
- GitHub Actions artifact with the same JSON payload in CI

Suggested structure:

```json
{
  "day": "2026-04-01",
  "platform": "default",
  "live": {
    "title": "...",
    "caption": "...",
    "hashtags": "...",
    "body_markdown": "...",
    "metrics_json": {
      "sections": {
        "caption": "...",
        "snapshot": "...",
        "affects": "...",
        "playbook": "..."
      }
    }
  },
  "candidate": {
    "title": "...",
    "caption": "...",
    "hashtags": "...",
    "body_markdown": "...",
    "metrics_json": {
      "sections": {
        "caption": "...",
        "snapshot": "...",
        "affects": "...",
        "playbook": "..."
      }
    }
  },
  "runtime": {
    "model": "...",
    "rewrite_used": true,
    "similarity_guard_triggered": false,
    "hook_rescue_triggered": false,
    "strategy": "candidate_public_caption_v1"
  }
}
```

## Minimal Implementation Shape

### Step 1

Add a shadow-only execution path in:

- `bots/earthscope_post/earthscope_generate.py`

Suggested control flags:

- `EARTHSCOPE_PUBLIC_SHADOW=true`
- `EARTHSCOPE_PUBLIC_SHADOW_OUTPUT=<path>`
- `EARTHSCOPE_PUBLIC_CANDIDATE_MODE=<name>`

### Step 2

Generate both outputs from the same `ctx`:

- live path
- candidate path

Do not publish the candidate.

### Step 3

Write the review bundle to JSON and optionally print a short diff summary to logs.

### Step 4

In GitHub Actions, upload the JSON as an artifact.

Primary workflow file:

- `.github/workflows/gaia_eyes_daily.yml`

## Recommended Diff Summary

Shadow mode logs should include:

- caption length delta
- whether title changed
- whether hashtags changed
- whether any required fields became empty
- whether `metrics_json.sections` keys were preserved

Do not rely on automated scoring alone for humor or founder-voice quality.

## Human Review Workflow

Each shadow run should be reviewed with four questions:

1. Which caption sounds more like the founder?
2. Which caption is more relevant to the actual day?
3. Did the candidate become more canned or more alive?
4. Did any structural field get worse for cards, reels, or posting?

## Golden Review Set

Before using shadow mode for rollout decisions, build a manual comparison set:

- best historical posts
- weak recent posts
- high-activity day examples
- low-activity day examples
- quiet-but-interesting days

Shadow mode should be judged against those examples, not only against today's live post.

## What To Freeze During Shadow Mode

Keep these unchanged while shadow mode is being built:

- `bots/earthscope_post/meta_poster.py`
- `bots/earthscope_post/reel_builder.py`
- `bots/earthscope_post/gaia_eyes_viral_bot.py`

Those consumers should be treated as fixed readers of the writer output.

## Candidate Strategies To Compare

Shadow mode is most useful if it can compare named strategies.

Suggested early strategies:

- `live_current`
- `public_draft_restored`
- `caption_only_rewrite`
- `example_driven_prompt`

The first production goal should be choosing the best caption strategy, not redesigning every section at once.

## Success Criteria

Shadow mode is ready when:

- it runs without publishing candidate output
- it captures both live and candidate bundles from the same input day
- it records enough runtime detail to explain differences
- it preserves the current field shape used by posting and media consumers
- it gives a human reviewer enough signal to approve or reject a voice change quickly

## Recommended Next Execution Order

1. Implement shadow mode JSON output in `earthscope_generate.py`.
2. Add artifact upload in `.github/workflows/gaia_eyes_daily.yml`.
3. Capture several days of live vs candidate output.
4. Approve a caption strategy.
5. Only after approval, wire the chosen candidate path into the live writer.
