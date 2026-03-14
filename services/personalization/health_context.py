from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


LEGACY_TAG_ALIASES = {
    "aqi_sensitive": "air_quality_sensitive",
    "temp_sensitive": "temperature_sensitive",
}

SENSITIVITY_KEYS = frozenset(
    {
        "air_quality_sensitive",
        "anxiety_sensitive",
        "geomagnetic_sensitive",
        "pressure_sensitive",
        "sleep_sensitive",
        "temperature_sensitive",
    }
)

HEALTH_CONTEXT_KEYS = frozenset(
    {
        "migraine_history",
        "chronic_pain",
        "arthritis",
        "fibromyalgia",
        "hypermobility_eds",
        "pots_dysautonomia",
        "mcas_histamine",
        "allergies_sinus",
        "asthma_breathing_sensitive",
        "heart_rhythm_sensitive",
        "autoimmune_condition",
        "nervous_system_dysregulation",
        "insomnia_sleep_disruption",
    }
)

HEAD_PRESSURE_KEYS = frozenset({"pressure_sensitive", "migraine_history"})
PAIN_FLARE_KEYS = frozenset(
    {
        "arthritis",
        "autoimmune_condition",
        "chronic_pain",
        "fibromyalgia",
        "hypermobility_eds",
    }
)
AUTONOMIC_KEYS = frozenset(
    {
        "heart_rhythm_sensitive",
        "nervous_system_dysregulation",
        "pots_dysautonomia",
    }
)
SINUS_KEYS = frozenset({"air_quality_sensitive", "allergies_sinus", "mcas_histamine"})
AIRWAY_KEYS = frozenset({"air_quality_sensitive", "asthma_breathing_sensitive", "mcas_histamine"})
SLEEP_DISRUPTION_KEYS = frozenset({"sleep_sensitive", "insomnia_sleep_disruption"})

PRESSURE_SIGNAL_KEYS = frozenset(
    {
        "earthweather.pressure_swing_12h",
        "earthweather.pressure_drop_3h",
        "earthweather.pressure_swing_24h_big",
    }
)
TEMP_SIGNAL_KEYS = frozenset(
    {
        "earthweather.temp_swing_24h",
        "earthweather.temp_swing_24h_big",
    }
)
AQI_SIGNAL_KEYS = frozenset({"earthweather.air_quality"})
GEOMAGNETIC_SIGNAL_KEYS = frozenset(
    {
        "spaceweather.kp",
        "spaceweather.sw_speed",
        "spaceweather.bz_coupling",
    }
)
SLEEP_CONTEXT_SIGNAL_KEYS = frozenset(set(GEOMAGNETIC_SIGNAL_KEYS) | {"schumann.variability_24h"})


def canonicalize_tag_key(value: Any) -> str:
    if value is None:
        return ""
    key = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    return LEGACY_TAG_ALIASES.get(key, key)


def _extract_tag_key(item: Any) -> str:
    if isinstance(item, str):
        return canonicalize_tag_key(item)
    if isinstance(item, Mapping):
        for field_name in ("tag_key", "key", "tag", "code", "tag_id"):
            if item.get(field_name) is not None:
                return canonicalize_tag_key(item.get(field_name))
    return canonicalize_tag_key(item)


def canonicalize_tag_keys(values: Iterable[Any] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values or []:
        key = _extract_tag_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


@dataclass(frozen=True)
class PersonalizationProfile:
    sensitivities: frozenset[str] = field(default_factory=frozenset)
    health_context: frozenset[str] = field(default_factory=frozenset)
    all_tags: frozenset[str] = field(default_factory=frozenset)

    def has_any(self, *keys: str) -> bool:
        return any(canonicalize_tag_key(key) in self.all_tags for key in keys)

    def includes_any(self, keys: Iterable[str]) -> bool:
        return any(canonicalize_tag_key(key) in self.all_tags for key in keys)


def build_personalization_profile(values: Iterable[Any] | None) -> PersonalizationProfile:
    normalized = frozenset(canonicalize_tag_keys(values))
    sensitivities = frozenset(key for key in normalized if key in SENSITIVITY_KEYS)
    health_context = frozenset(key for key in normalized if key in HEALTH_CONTEXT_KEYS)
    return PersonalizationProfile(
        sensitivities=sensitivities,
        health_context=health_context,
        all_tags=normalized,
    )


def gauge_personalization_multiplier(
    profile: PersonalizationProfile,
    *,
    signal_key: str,
    gauge_key: str,
) -> float:
    if not profile.all_tags:
        return 1.0

    multiplier = 1.0

    # Keep boosts small and bounded so the base scoring definition still dominates.
    if signal_key in PRESSURE_SIGNAL_KEYS:
        if gauge_key in {"pain", "focus", "mood"} and profile.includes_any(HEAD_PRESSURE_KEYS):
            multiplier += 0.25
        if gauge_key in {"pain", "energy", "stamina"} and profile.includes_any(PAIN_FLARE_KEYS):
            multiplier += 0.20

    if signal_key in TEMP_SIGNAL_KEYS and gauge_key in {"pain", "energy", "stamina"}:
        if profile.includes_any(PAIN_FLARE_KEYS):
            multiplier += 0.20

    if signal_key in GEOMAGNETIC_SIGNAL_KEYS and gauge_key in {"heart", "energy", "stamina"}:
        if profile.includes_any(AUTONOMIC_KEYS):
            multiplier += 0.25

    if signal_key in AQI_SIGNAL_KEYS:
        if gauge_key in {"energy", "mood", "health_status"} and (
            profile.includes_any(SINUS_KEYS) or profile.includes_any(AIRWAY_KEYS)
        ):
            multiplier += 0.20
        if gauge_key == "focus" and (profile.includes_any(SINUS_KEYS) or profile.includes_any(AIRWAY_KEYS)):
            multiplier += 0.10

    if signal_key in SLEEP_CONTEXT_SIGNAL_KEYS and gauge_key in {"sleep", "energy", "mood"}:
        if profile.includes_any(SLEEP_DISRUPTION_KEYS):
            multiplier += 0.25

    return min(multiplier, 1.6)


def health_status_contextual_adjustment(
    profile: PersonalizationProfile,
    active_states: Iterable[Mapping[str, Any]] | None,
) -> float:
    if not profile.includes_any(SINUS_KEYS) and not profile.includes_any(AIRWAY_KEYS):
        return 0.0

    state_weights = {
        "moderate": 1.0,
        "usg": 2.5,
        "unhealthy": 4.0,
    }
    max_adjustment = 0.0
    for state in active_states or []:
        if canonicalize_tag_key(state.get("signal_key")) not in AQI_SIGNAL_KEYS:
            continue
        state_name = str(state.get("state") or "").strip().lower()
        max_adjustment = max(max_adjustment, state_weights.get(state_name, 0.0))
    # Health Status remains primarily wearable/symptom driven; AQI context only nudges it slightly.
    return min(max_adjustment, 4.0)
