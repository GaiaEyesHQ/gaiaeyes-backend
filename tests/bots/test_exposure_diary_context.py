from datetime import datetime, timedelta, timezone
import sys
import types

if "services.db" not in sys.modules:
    db_stub = types.ModuleType("services.db")

    class _PgStub:
        def fetch(self, *args, **kwargs):
            return []

        def fetchrow(self, *args, **kwargs):
            return None

        def execute(self, *args, **kwargs):
            return None

    db_stub.pg = _PgStub()
    sys.modules["services.db"] = db_stub
if "bots.gauges.signal_resolver" not in sys.modules:
    resolver_stub = types.ModuleType("bots.gauges.signal_resolver")
    resolver_stub.resolve_signals = lambda *args, **kwargs: {}
    sys.modules["bots.gauges.signal_resolver"] = resolver_stub
if "bots.gauges.local_payload" not in sys.modules:
    local_payload_stub = types.ModuleType("bots.gauges.local_payload")
    local_payload_stub.get_local_payload = lambda *args, **kwargs: {}
    sys.modules["bots.gauges.local_payload"] = local_payload_stub

from bots.gauges.gauge_scorer import _build_exposure_signal_summary
from bots.patterns.pattern_engine_job import build_user_daily_features
from services.personalization.health_context import build_personalization_profile


def test_everyday_exposure_has_conservative_gauge_context():
    asof = datetime(2026, 6, 10, 18, tzinfo=timezone.utc)
    summary = _build_exposure_signal_summary(
        [
            {
                "exposure_key": "fragrance_scented_products",
                "intensity": 3,
                "event_ts_utc": asof - timedelta(hours=2),
                "source": "manual",
                "note_text": None,
            }
        ],
        asof=asof,
        profile=build_personalization_profile([]),
    )

    assert summary["top_exposures"][0]["exposure_key"] == "fragrance_scented_products"
    assert summary["gauge_boosts"]["health_status"] <= 6.0
    assert summary["gauge_boosts"]["energy"] < 2.0


def test_pattern_feature_rows_carry_everyday_exposure_context_without_signal_definition():
    day = datetime(2026, 6, 10, tzinfo=timezone.utc).date()
    rows = build_user_daily_features(
        base_rows=[{"user_id": "user-1", "day": day}],
        gauges={},
        gauge_deltas={},
        symptom_stats={},
        camera_rows={},
        tag_flags={},
        day_zip_map={},
        current_zip_map={},
        local_signals_daily={},
        schumann_daily={},
        updated_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        exposure_context={
            ("user-1", day): {
                "everyday_exposure_reported": True,
            }
        },
    )

    assert rows[0]["everyday_exposure_reported"] is True
