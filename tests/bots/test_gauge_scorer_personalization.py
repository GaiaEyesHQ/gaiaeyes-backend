import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.definitions.load_definition_base import load_definition_base
try:
    from bots.gauges.gauge_scorer import _score_gauges
    from services.personalization.health_context import (
        build_personalization_profile,
        health_status_contextual_adjustment,
    )
    _IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # pragma: no cover - local runtimes may not include DB deps.
    _IMPORT_ERROR = exc


@unittest.skipIf(_IMPORT_ERROR is not None, f"Gauge scorer personalization tests require optional dependencies: {_IMPORT_ERROR}")
class GaugeScorerPersonalizationTests(unittest.TestCase):
    def test_pressure_profile_raises_pain_focus_and_mood_weights(self) -> None:
        definition, _ = load_definition_base()
        active_states = [{"signal_key": "earthweather.pressure_drop_3h", "state": "watch"}]

        baseline = _score_gauges(definition, active_states)
        personalized = _score_gauges(
            definition,
            active_states,
            profile=build_personalization_profile(["pressure_sensitive"]),
        )

        self.assertGreater(personalized["pain"], baseline["pain"])
        self.assertGreater(personalized["focus"], baseline["focus"])
        self.assertGreater(personalized["mood"], baseline["mood"])
        self.assertEqual(personalized["sleep"], baseline["sleep"])

    def test_autonomic_profile_raises_heart_energy_and_stamina_weights(self) -> None:
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

        self.assertGreater(personalized["heart"], baseline["heart"])
        self.assertGreater(personalized["energy"], baseline["energy"])
        self.assertGreater(personalized["stamina"], baseline["stamina"])

    def test_air_quality_context_can_nudge_health_status(self) -> None:
        adjustment = health_status_contextual_adjustment(
            build_personalization_profile(["allergies_sinus"]),
            [{"signal_key": "earthweather.air_quality", "state": "unhealthy"}],
        )

        self.assertGreater(adjustment, 0)
        self.assertLessEqual(adjustment, 4.0)

    def test_allergen_profile_raises_pain_focus_and_energy_weights(self) -> None:
        definition, _ = load_definition_base()
        active_states = [{"signal_key": "earthweather.allergens", "state": "high"}]

        baseline = _score_gauges(definition, active_states)
        personalized = _score_gauges(
            definition,
            active_states,
            profile=build_personalization_profile(["allergies_sinus", "migraine_history"]),
        )

        self.assertGreater(personalized["pain"], baseline["pain"])
        self.assertGreater(personalized["focus"], baseline["focus"])
        self.assertGreater(personalized["energy"], baseline["energy"])
