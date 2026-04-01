# Voice Matrix Draft

This document defines the target voice system for Gaia Eyes.

The goal is not one voice. The goal is one truth system with controlled voice variants.

## Core Principle

Gaia Eyes should separate:

- what is true
- how it is said

The same daily meaning should be renderable in:

- app, scientific, straight
- app, scientific, humorous, robot
- app, mystical, balanced, cat
- social, public playful brand voice

without changing the underlying facts, confidence, or caution level.

## Voice Stack

Voice should be applied in this order:

1. Semantic truth
   Facts, drivers, patterns, confidence, actions, and caveats.
2. Mode vocabulary
   Scientific vs mystical labeling only.
3. Tone
   Straight, balanced, humorous.
4. Persona
   Cat, robot, dog, or no persona.
5. Channel rules
   App, social, push, dashboard, web detail.

This order matters.

- Mode should change vocabulary, not evidence.
- Tone should change rhythm and warmth, not claims.
- Persona should add flavor, not rewrite meaning.
- Channel should control packaging, not truth.

## Non-Negotiable Voice Rules

1. Facts stay invariant across all renderers.
2. Confidence stays invariant across all renderers.
3. Humor cannot increase urgency.
4. Mystical mode cannot imply stronger evidence than scientific mode.
5. Persona should be light enough that serious moments still feel trustworthy.
6. Social can be more playful than app, but not more dramatic than the evidence supports.
7. Fear-mongering is disallowed across all channels.

## Target Voice Dimensions

| Dimension | Scientific | Mystical |
| --- | --- | --- |
| Vocabulary | metrics, drivers, patterns, pressure swing, geomagnetic activity | translated, intuitive labels, what is shaping today, magnetic weather, Earth resonance |
| Claim style | plain, bounded, evidence-forward | interpretive, intuitive, still bounded |
| Metaphor use | rare | moderate |
| Reader promise | orientation and clarity | orientation and felt translation |

| Dimension | Straight | Balanced | Humorous |
| --- | --- | --- | --- |
| Rhythm | shortest | medium | medium-short |
| Warmth | low | medium | medium |
| Humor | none | occasional softness | light recurring wit |
| Use case | quick read | default app tone | personality without noise |

| Persona | Role | Humor style | Risk to avoid |
| --- | --- | --- | --- |
| Cat | observant, wry, calm | sly, understated | sounding vague or overly mystical by default |
| Robot | precise, dry, data-forward | deadpan, clipped | sounding cold or clinical |
| Dog | steady, grounded, reassuring | gentle, loyal-energy | sounding overly cheerful when user may feel bad |
| None / social narrator | branded public voice | playful, clean, internet-friendly | over-branding or sounding like marketing copy |

## Recommended Defaults

### In-App Defaults

- Default mode: `scientific`
- Default tone: `balanced`
- Default guide: `cat`

Why:

- this keeps the first-run experience grounded
- it leaves room for mystical vocabulary and stronger persona expression as an opt-in

### Social Default

- Channel profile: `public_playful`
- Vocabulary basis: mostly scientific plain-language
- Tone basis: humorous-balanced hybrid
- Persona: none

Why:

- social should feel branded, playful, and legible to people who have not chosen a guide or mode
- social should not inherit a specific user profile voice

## Render Precedence

When multiple settings apply, render in this precedence:

1. Channel safety rules
2. Confidence / caution rules
3. Mode vocabulary
4. Tone rhythm
5. Persona flavor

Example:

- scientific + humorous + robot
  - still uses scientific vocabulary
  - still preserves caution phrases
  - humor becomes dry/deadpan, not whimsical

## Voice Profiles

These are the recommended target profiles.

### App Scientific Straight

- Use plain labels
- Prefer short sentences
- Prefer direct observational verbs
- Minimal metaphor
- Minimal persona expression

Example style:

- "Pressure swing is one of the louder drivers today."
- "You may notice more tension or headache sensitivity."

### App Scientific Balanced

- Same facts as straight
- Slightly warmer transitions
- Brief supportive action language
- Persona can show lightly

Example style:

- "Pressure swing looks like one of the main drivers today."
- "If you're sensitive to it, your head or energy may feel a little less settled."

### App Scientific Humorous

- Same facts and confidence
- Humor is small and controlled
- Good place for robot deadpan or cat slyness

Example style:

- Robot: "Pressure swing is doing enough today to earn a mention."
- Cat: "Pressure swing seems interested in being noticed."

### App Mystical Straight

- Use translated vocabulary
- Keep sentence structure simple
- No dramatic mysticism

Example style:

- "Magnetic weather is one of the stronger influences today."
- "You may feel a little less settled or more sensitive than usual."

### App Mystical Balanced

- Default mystical target
- Gentle symbolism allowed
- Still bounded and practical

Example style:

- "The field looks a little louder today, so your system may feel more reactive."
- "Treat it as context, not destiny."

### App Mystical Humorous

- Warm, lightly symbolic, playful
- Humor stays soft

Example style:

- "The field has opinions today."
- "You do not need to match its energy."

### Social Public Playful

- One stable public voice
- No user-profile dependency
- Mostly scientific plain-language under the hood
- Light humor, no doom
- Strong readability
- CTA should help people pace, not panic

Example style:

- "Space weather is a little louder today. If your sleep, head, or focus feel off, you are not imagining it."
- "Keep the drama lower than the data."

## Claim Language Ladder

Use these verbs by evidence level, regardless of voice.

| Confidence / evidence | Allowed language | Avoid |
| --- | --- | --- |
| Low | may line up with, may notice, worth watching | is causing, means, confirms |
| Moderate | often lines up with, can be noticeable, has shown up before | clearly causes, strongly proves |
| High | has repeatedly lined up with, is one of the stronger signals today | guarantees, explains everything |

This should be enforced before voice rendering, not after.

## Humor Guardrails

Allowed:

- dry understatement
- light irony
- gentle anthropomorphism
- tension release

Avoid:

- jokes that trivialize symptoms
- apocalypse framing
- "your body is broken" tone
- fear-based hooks
- sarcasm aimed at the user

## Persona Rules

Persona should mainly affect:

- opener
- transitions
- occasional phrasing choice
- cadence

Persona should not affect:

- thresholds
- confidence wording
- action recommendations
- risk framing

## Channel Rules

| Channel | Goal | Preferred length | Persona strength | Humor strength |
| --- | --- | --- | --- | --- |
| App summary card | quick orientation | short | low | low-medium |
| App detail / EarthScope | readable interpretation | medium | medium | low-medium |
| Current Symptoms / body flows | trust and clarity | short-medium | low | low |
| Notifications | calm utility | short | very low | very low |
| Social caption | branded engagement | short-medium | none | medium |
| Web dashboard | member readability | medium | low | low-medium |

## Recommended First Implementation Target

Do not start by rewriting every string.

Start by moving these surfaces onto the shared voice stack first:

1. home EarthScope summary
2. full member EarthScope
3. What Matters Now
4. share captions
5. driver short reason / personal reason

These five surfaces currently create most of the voice fragmentation.

## Example Matrix

| Semantic input | App scientific straight | App scientific humorous robot | App mystical balanced cat | Social public playful |
| --- | --- | --- | --- | --- |
| Pressure is the main driver, confidence moderate, pacing recommended | "Pressure swing is one of the main drivers today. You may notice more tension or headache sensitivity. Keep the day a little lighter if you can." | "Pressure swing is doing enough today to qualify as a problem. Head or tension sensitivity may be more noticeable. Conservative pacing would be efficient." | "Pressure shift looks active today. Your system may feel a little more reactive or head-heavy than usual. Take the day a bit more gently if you can." | "Pressure is one of the louder signals today. If your head or tension levels feel extra dramatic, there is at least a decent suspect. Pace a little smarter, not scarier." |

## Draft Recommendation

Adopt one internal phrase for this system:

- `semantic truth, expressive render`

That phrase is simple enough to keep implementation decisions honest later.
