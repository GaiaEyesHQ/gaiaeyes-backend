import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.migraine.episode_contract import MigraineEpisode


FIXTURES = ROOT / "tests" / "fixtures" / "migraine_episode_contract"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize("name", ["live_siri_episode.json", "generic_import_episode.json"])
def test_synthetic_episode_fixtures_validate(name: str) -> None:
    episode = MigraineEpisode.model_validate(load_fixture(name))

    assert episode.symptom_code == "MIGRAINE"
    assert episode.start.utc.utcoffset().total_seconds() == 0


def test_resolved_episode_rejects_end_before_start() -> None:
    payload = load_fixture("live_siri_episode.json")
    payload["end"]["utc"] = "2026-08-14T12:00:00Z"

    with pytest.raises(ValidationError, match="end cannot be earlier than start"):
        MigraineEpisode.model_validate(payload)


def test_live_episode_requires_existing_symptom_event_link() -> None:
    payload = load_fixture("live_siri_episode.json")
    payload["symptom_event_id"] = None

    with pytest.raises(ValidationError, match="live episodes require symptom_event_id linkage"):
        MigraineEpisode.model_validate(payload)


def test_import_requires_reversible_provenance() -> None:
    payload = load_fixture("generic_import_episode.json")
    payload["provenance"].pop("import_run_id")

    with pytest.raises(ValidationError, match="import provenance missing: import_run_id"):
        MigraineEpisode.model_validate(payload)


def test_optional_dose_is_complete_or_absent() -> None:
    payload = load_fixture("live_siri_episode.json")
    payload["medicines"][0].pop("dose_unit")

    with pytest.raises(ValidationError, match="dose_amount and dose_unit must be supplied together"):
        MigraineEpisode.model_validate(payload)


def test_unknown_fields_are_rejected_to_prevent_silent_mapping_loss() -> None:
    payload = load_fixture("generic_import_episode.json")
    payload["provider_guess"] = "not part of the contract"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MigraineEpisode.model_validate(payload)
