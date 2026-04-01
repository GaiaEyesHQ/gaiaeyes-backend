# Semantic Schema Draft

This document defines the shared meaning payload that Gaia Eyes renderers should consume.

The schema is intentionally voice-free.

It should answer:

- what happened
- what matters most
- what the user may notice
- what to do with that information
- how certain the app is

without deciding final wording.

## Design Goal

One canonical semantic payload should feed:

- app summary cards
- full EarthScope
- What Matters Now
- Current Symptoms context
- driver details
- pattern summaries
- social captions
- push notifications

The renderer should decide tone and packaging later.

## Schema Principles

1. Facts and interpretation are separate fields.
2. Confidence is explicit.
3. Claims are bounded by evidence level.
4. Action suggestions are separate from explanation.
5. Channel-specific formatting is not stored in the core payload.
6. Persona-specific jokes or flourishes are not stored in the core payload.

## Top-Level Shape

```json
{
  "schema_version": "1.0",
  "kind": "daily_state",
  "date": "2026-04-01",
  "user_context": {},
  "facts": {},
  "interpretation": {},
  "actions": {},
  "guardrails": {},
  "render_hints": {}
}
```

## Top-Level Fields

### `schema_version`

- string
- increment only when semantic meaning changes, not when wording changes

### `kind`

Allowed initial values:

- `daily_state`
- `earthscope_summary`
- `earthscope_detail`
- `driver_detail`
- `pattern_summary`
- `symptom_context`
- `outlook_window`
- `share_caption_seed`

### `date`

- ISO date for the payload's target day

### `user_context`

User-specific context that affects interpretation but is not phrasing:

```json
{
  "mode": "scientific",
  "guide": "robot",
  "tone": "humorous",
  "temp_unit": "F",
  "has_health_data": true,
  "has_location": true
}
```

Note:

- social/public renderers should ignore user-specific voice choices
- this block exists for app and member contexts

## `facts`

Raw or normalized observations that the renderer may need to mention.

Suggested shape:

```json
{
  "signals": [
    {
      "key": "pressure",
      "label": "Pressure Swing",
      "value": -8.4,
      "unit": "hPa",
      "state": "watch",
      "trend": "falling",
      "threshold_crossed": true,
      "as_of": "2026-04-01T13:00:00Z"
    }
  ],
  "gauges": [
    {
      "key": "energy",
      "value": 42,
      "zone": "strained",
      "delta": -8,
      "recent_symptom_boost": 6
    }
  ],
  "symptoms": {
    "active_count": 2,
    "current_states": ["active", "improving"],
    "top_items": ["headache", "fatigue"]
  },
  "patterns": {
    "active_count": 1,
    "top_pattern_keys": ["pressure_headache_24h"]
  }
}
```

Rules:

- `facts` should be declarative, not interpretive
- labels here are stable system labels, not final user-facing prose

## `interpretation`

This is the meaning layer.

Suggested shape:

```json
{
  "primary_driver": {
    "key": "pressure",
    "strength": 0.78,
    "personal_relevance": 0.72,
    "confidence": "moderate",
    "why_now": [
      "current_signal_strength",
      "pattern_history",
      "recent_symptom_overlap"
    ]
  },
  "supporting_drivers": [
    {
      "key": "aqi",
      "strength": 0.44,
      "personal_relevance": 0.39,
      "confidence": "low"
    }
  ],
  "body_themes": [
    {
      "key": "head_tension",
      "likelihood": "moderate",
      "confidence": "moderate"
    },
    {
      "key": "drained_energy",
      "likelihood": "low",
      "confidence": "low"
    }
  ],
  "summary_priority": "pressure",
  "narrative_weight": "watch"
}
```

Rules:

- this layer can say what matters most
- this layer cannot emit final phrasing
- `why_now` should be machine-readable so later audits can trace why something was emphasized

## `actions`

Action suggestions should be explicit and separately ranked.

Suggested shape:

```json
{
  "primary": [
    {
      "key": "pace_lower",
      "priority": 1,
      "reason": "pressure"
    },
    {
      "key": "hydrate",
      "priority": 2,
      "reason": "head_tension"
    }
  ],
  "secondary": [
    {
      "key": "reduce_overload",
      "priority": 3,
      "reason": "energy"
    }
  ]
}
```

Rules:

- actions should not be embedded inside interpretation prose
- actions should be reusable across channels

## `guardrails`

This is where confidence, claim strength, and safety limits live.

Suggested shape:

```json
{
  "confidence_overall": "moderate",
  "claim_strength": "may_notice",
  "evidence_basis": [
    "live_signal_threshold",
    "personal_pattern_history"
  ],
  "medical_disclaimer_level": "light",
  "avoid_fear_language": true,
  "avoid_causal_language": true,
  "max_urgency": "watch"
}
```

Recommended `claim_strength` enum:

- `observe_only`
- `may_notice`
- `likely_notice`
- `strong_repeat_pattern`

Important:

- renderer must not exceed `claim_strength`
- humorous renderers still obey `max_urgency` and `avoid_fear_language`

## `render_hints`

This section is optional and should only contain packaging hints that do not alter truth.

Suggested shape:

```json
{
  "preferred_summary_length": "short",
  "preferred_detail_sections": [
    "what_is_active",
    "what_you_may_notice",
    "what_may_help"
  ],
  "humor_ok": true,
  "metaphor_ok": false,
  "persona_strength": "light"
}
```

Rules:

- hints help renderer shape output
- hints do not authorize stronger claims

## Supporting Enums

### Signal State

- `quiet`
- `mild`
- `watch`
- `high`

### Confidence

- `low`
- `moderate`
- `high`

### Narrative Weight

- `quiet`
- `notable`
- `watch`
- `high`

### Likelihood

- `low`
- `moderate`
- `high`

## Semantic Objects

### Driver Object

```json
{
  "key": "pressure",
  "strength": 0.78,
  "personal_relevance": 0.72,
  "confidence": "moderate",
  "source_types": ["live_signal", "pattern_history"],
  "linked_gauges": ["pain", "energy"],
  "linked_body_themes": ["head_tension"]
}
```

### Pattern Object

```json
{
  "key": "pressure_headache_24h",
  "signal_key": "pressure",
  "outcome_key": "headache_day",
  "lag_hours": 24,
  "evidence_count": 9,
  "relative_lift": 1.7,
  "confidence": "moderate",
  "active_today": true
}
```

### Symptom Context Object

```json
{
  "top_current_symptoms": ["headache", "fatigue"],
  "active_episode_states": ["active", "improving"],
  "severity_band": "moderate",
  "gauge_effects": [
    {"key": "pain", "points": 8},
    {"key": "energy", "points": 4}
  ]
}
```

## Example Daily Payload

```json
{
  "schema_version": "1.0",
  "kind": "daily_state",
  "date": "2026-04-01",
  "user_context": {
    "mode": "scientific",
    "guide": "robot",
    "tone": "humorous",
    "temp_unit": "F",
    "has_health_data": true,
    "has_location": true
  },
  "facts": {
    "signals": [
      {
        "key": "pressure",
        "label": "Pressure Swing",
        "value": -8.4,
        "unit": "hPa",
        "state": "watch",
        "trend": "falling",
        "threshold_crossed": true,
        "as_of": "2026-04-01T13:00:00Z"
      }
    ],
    "gauges": [
      {
        "key": "pain",
        "value": 63,
        "zone": "elevated",
        "delta": 7,
        "recent_symptom_boost": 8
      },
      {
        "key": "energy",
        "value": 42,
        "zone": "strained",
        "delta": -8,
        "recent_symptom_boost": 4
      }
    ],
    "symptoms": {
      "active_count": 2,
      "current_states": ["active", "improving"],
      "top_items": ["headache", "fatigue"]
    },
    "patterns": {
      "active_count": 1,
      "top_pattern_keys": ["pressure_headache_24h"]
    }
  },
  "interpretation": {
    "primary_driver": {
      "key": "pressure",
      "strength": 0.78,
      "personal_relevance": 0.72,
      "confidence": "moderate",
      "why_now": [
        "current_signal_strength",
        "pattern_history",
        "recent_symptom_overlap"
      ]
    },
    "supporting_drivers": [
      {
        "key": "aqi",
        "strength": 0.44,
        "personal_relevance": 0.39,
        "confidence": "low"
      }
    ],
    "body_themes": [
      {
        "key": "head_tension",
        "likelihood": "moderate",
        "confidence": "moderate"
      },
      {
        "key": "drained_energy",
        "likelihood": "low",
        "confidence": "low"
      }
    ],
    "summary_priority": "pressure",
    "narrative_weight": "watch"
  },
  "actions": {
    "primary": [
      {"key": "pace_lower", "priority": 1, "reason": "pressure"},
      {"key": "hydrate", "priority": 2, "reason": "head_tension"}
    ],
    "secondary": [
      {"key": "reduce_overload", "priority": 3, "reason": "energy"}
    ]
  },
  "guardrails": {
    "confidence_overall": "moderate",
    "claim_strength": "may_notice",
    "evidence_basis": ["live_signal_threshold", "personal_pattern_history"],
    "medical_disclaimer_level": "light",
    "avoid_fear_language": true,
    "avoid_causal_language": true,
    "max_urgency": "watch"
  },
  "render_hints": {
    "preferred_summary_length": "short",
    "preferred_detail_sections": [
      "what_is_active",
      "what_you_may_notice",
      "what_may_help"
    ],
    "humor_ok": true,
    "metaphor_ok": false,
    "persona_strength": "light"
  }
}
```

## Renderer Contract

Each renderer should accept:

- semantic payload
- channel
- mode
- tone
- guide or public narrator profile

and produce text without mutating the payload.

Pseudo-shape:

```json
{
  "renderer_input": {
    "channel": "app_detail",
    "mode": "scientific",
    "tone": "humorous",
    "guide": "robot",
    "payload": "{semantic_payload}"
  }
}
```

## Recommended First Adopters

Use this schema first for:

1. EarthScope summary
2. member EarthScope detail
3. What Matters Now
4. driver short reason / personal reason
5. share captions

These five surfaces will prove whether the semantic layer is actually strong enough to unify voice.

## Draft Recommendation

When implementing this later, do not put prose templates inside the schema.

If a field sounds like final copy instead of meaning, it probably belongs in the renderer, not in the semantic payload.
