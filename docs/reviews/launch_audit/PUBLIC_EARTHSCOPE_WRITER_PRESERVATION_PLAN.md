# Public EarthScope Writer Preservation Plan

This plan is for the auto-posting public EarthScope writer only.

It does not cover:

- in-app share captions
- member EarthScope
- app EarthScope detail copy

## Objective

Improve the public EarthScope writer without flattening its personality or breaking the publishing, overlay, or reel pipeline.

## Primary Rule

Preserve the interface. Change the voice behind it carefully.

The public writer is allowed to sound different from the app. It should sound more like the founder voice:

- playful
- specific
- lightly funny
- internet-readable
- not fear-based
- not canned

## Current Live Contract

The following outputs are currently depended on by downstream systems and should be treated as frozen interfaces during voice work:

- `content.daily_posts.title`
- `content.daily_posts.caption`
- `content.daily_posts.body_markdown`
- `content.daily_posts.hashtags`
- `content.daily_posts.metrics_json`
- `content.daily_posts.metrics_json.sections.caption`
- `content.daily_posts.metrics_json.sections.snapshot`
- `content.daily_posts.metrics_json.sections.affects`
- `content.daily_posts.metrics_json.sections.playbook`

Primary files:

- `bots/earthscope_post/earthscope_generate.py`
- `bots/earthscope_post/meta_poster.py`
- `bots/earthscope_post/reel_builder.py`
- `bots/earthscope_post/gaia_eyes_viral_bot.py`
- `.github/workflows/gaia_eyes_daily.yml`

## What Appears To Have Flattened The Voice

### 1. The deterministic draft became more standardized

Recent unification moved the public seed copy to:

- `services/voice/earthscope_posts.py`

That renderer is useful for shared truth, but it is noticeably more standardized than the older public-specific draft seed that lived directly in:

- `bots/earthscope_post/earthscope_generate.py`

Result:

- cleaner semantics
- less idiosyncratic phrasing
- weaker raw material for the rewrite step

### 2. The rewrite path has too many sanding layers

Current public caption generation in `bots/earthscope_post/earthscope_generate.py` passes through:

- deterministic rule copy
- interpretive JSON rewrite
- numeric sentence stripping
- validation gate
- similarity guard
- hook replacement
- banned phrase scrub
- metric footer injection

Each step is reasonable in isolation. Together they increase the chance that the output sounds safe, repetitive, and over-managed.

### 3. Humor is being sourced from helper lists instead of voice examples

The current writer leans on fixed pools like:

- `HOOKS`
- `METAPHOR_HINTS`

This is useful as a rescue system, but it tends to produce humor that feels generic or preloaded instead of situational.

## Preservation Goals

The next public-writer phase should preserve all of the following:

- same publishing workflow
- same DB schema
- same downstream image/reel/post consumers
- same section keys inside `metrics_json.sections`
- same general safety and non-fear guardrails

It should improve:

- humor relevance
- specificity
- phrasing variation
- founder-voice resemblance
- reduction of canned opening lines

## Non-Goals

Do not do these in the first preservation pass:

- do not rewrite the Meta posting pipeline
- do not change the reel builder contract
- do not change image-card file names
- do not add a second persistent content table without explicit approval
- do not make the public writer sound like the app
- do not merge public voice into the guide/persona voice system

## Recommended Architecture Direction

Keep one semantic truth layer, but allow the public writer to have its own draft renderer.

Recommended layers:

1. Semantic truth
   Shared facts, bands, caution level, driver bits, actions.
2. Public draft renderer
   A founder-voice seed written specifically for public social captioning.
3. LLM polish layer
   Rewrites or tightens only where helpful.
4. Post-process safety layer
   Minimal cleanup, not broad personality replacement.

## Recommended Scope Split

### Keep deterministic and stable

These are the best candidates to stay mostly deterministic:

- `snapshot`
- `affects`
- `playbook`
- `metrics_json.sections.*`

Reason:

- these feed cards and downstream media
- they benefit more from clarity and consistency than from creative style

### Let voice live primarily in these

- `caption`
- `title`

Reason:

- this is where the public post actually feels like a person
- this is where humor and tone matter most
- this is the lowest-risk place to restore personality without destabilizing the card pipeline

## Safe Change Surface

These are the safest places to change first:

- the public-specific draft text used before the LLM rewrite
- the prompt examples used by the rewrite
- the title-generation prompt
- the fallback ordering between public draft and rewrite output

Primary file:

- `bots/earthscope_post/earthscope_generate.py`

## Change With Care

These are safe only if shape is preserved exactly:

- `metrics_json.sections.caption`
- `body_markdown` section headings and section extraction behavior
- reel VO caption sanitation assumptions

Primary files:

- `bots/earthscope_post/gaia_eyes_viral_bot.py`
- `bots/earthscope_post/reel_builder.py`
- `bots/earthscope_post/meta_poster.py`

## Do Not Change In The First Pass

- `meta_poster.py`
- `reel_builder.py`
- workflow structure in `.github/workflows/gaia_eyes_daily.yml`

Unless there is a direct bug, these should be frozen while voice work is evaluated.

## Recommended Recovery Strategy

### Phase A: Capture the good voice before changing code

Build a review set of:

- 10 to 20 older public EarthScope captions that sounded right
- 10 recent captions that sound too scripted
- 10 examples of humor that feels relevant
- 10 examples of humor that feels canned

This becomes the human approval set for the writer.

### Phase B: Restore a public-specific draft layer

Do not remove semantic truth.

Do restore a distinct public draft seed in:

- `bots/earthscope_post/earthscope_generate.py`

That draft should be:

- more situational
- less standardized
- less app-like
- less obviously templated

### Phase C: Reduce rescue helpers to fallback-only

The following should be demoted from main personality sources to fallback tools:

- `HOOKS`
- `METAPHOR_HINTS`
- automatic rehooking for non-bad outputs

### Phase D: Swap style constraints for example-driven guidance

The LLM should get:

- good output examples
- bad output examples
- hard safety rules

It should get fewer canned humor devices.

## Approval Checklist For Public Voice

Every candidate public-writer change should be reviewed against:

- Does it sound like a person, not a prompt stack?
- Is the humor situational instead of generic?
- Does it avoid fear amplification?
- Does it avoid sounding like app copy pasted into social?
- Does it preserve the same actual facts as the live version?
- Would the founder plausibly write or approve this line?

## Suggested Execution Order

1. Add shadow mode for non-publishing comparison.
2. Capture goldens and anti-goldens.
3. Restore a public-specific draft layer.
4. Evaluate caption-only output first.
5. Evaluate title output second.
6. Leave `snapshot`, `affects`, and `playbook` mostly stable until caption voice is recovered.
7. Only then consider whether longer section voice should be loosened.

## Exit Criteria

This phase is successful when:

- the writer still publishes through the current pipeline unchanged
- captions sound less canned and more founder-like
- overlay and reel generation keep working without field changes
- humorous lines feel relevant to the day, not grabbed from a static bank
- the public writer remains distinct from in-app voice without drifting into fear or fluff
