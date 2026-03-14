import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.definitions.load_definition_base import load_definition_base
from bots.gauges.gauge_scorer import _score_gauges
from services.personalization.health_context import (
    build_personalization_profile,
    health_status_contextual_adjustment,
)


def test_pressure_profile_raises_pain_focus_and_mood_weights() -> None:
    definition, _ = load_definition_base()
    active_states = [{"signal_key": "earthweather.pressure_drop_3h", "state": "watch"}]

    baseline = _score_gauges(definition, active_states)
    personalized = _score_gauges(
        definition,
        active_states,
        profile=build_personalization_profile(["pressure_sensitive"]),
    )

    assert personalized["pain"] > baseline["pain"]
    assert personalized["focus"] > baseline["focus"]
    assert personalized["mood"] > baseline["mood"]
    assert personalized["sleep"] == baseline["sleep"]


def test_autonomic_profile_raises_heart_energy_and_stamina_weights() -> None:
    definition, _ = load_definition_base()
    active_states = [
        {"signal_key": "spaceweather.kp", "state": "storm"},
        {"signal_key": "spaceweather.bz_coupling", "state": "strong"},
    ]

    baseline = _score_gauges(definition, active_states)
    personalized = _score_gauges(
        definition,
        active_states,
        profile=build_personalization_profile(["pots_dysautonomia"]),
    )

    assert personalized["heart"] > baseline["heart"]
    assert personalized["energy"] > baseline["energy"]
    assert personalized["stamina"] > baseline["stamina"]


def test_air_quality_context_can_nudge_health_status() -> None:
    adjustment = health_status_contextual_adjustment(
        build_personalization_profile(["allergies_sinus"]),
        [{"signal_key": "earthweather.air_quality", "state": "unhealthy"}],
    )

    assert adjustment > 0
    assert adjustment <= 4.0
