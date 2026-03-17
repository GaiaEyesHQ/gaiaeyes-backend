from datetime import datetime, timezone

from bots.notifications.push_logic import (
    allows_severity,
    build_dedupe_key,
    can_emit_with_cooldown,
    dedupe_bucket_start,
    flare_class_rank,
    gauge_zone,
    is_within_quiet_hours,
    previous_gauge_value,
)


def test_minimal_sensitivity_only_allows_high() -> None:
    assert allows_severity("minimal", "high") is True
    assert allows_severity("minimal", "watch") is False
    assert allows_severity("normal", "watch") is True
    assert allows_severity("detailed", "watch") is True


def test_quiet_hours_handle_overnight_window() -> None:
    now = datetime(2026, 3, 17, 4, 30, tzinfo=timezone.utc)
    assert is_within_quiet_hours(
        now,
        enabled=True,
        time_zone_name="UTC",
        quiet_start="22:00",
        quiet_end="08:00",
    )
    assert not is_within_quiet_hours(
        datetime(2026, 3, 17, 15, 0, tzinfo=timezone.utc),
        enabled=True,
        time_zone_name="UTC",
        quiet_start="22:00",
        quiet_end="08:00",
    )


def test_geomagnetic_dedupe_bucket_uses_family_cooldown() -> None:
    now = datetime(2026, 3, 17, 14, 37, tzinfo=timezone.utc)
    bucket = dedupe_bucket_start(now, "geomagnetic")
    assert bucket == datetime(2026, 3, 17, 12, 0, tzinfo=timezone.utc)
    assert build_dedupe_key("user-1", "geomagnetic", "kp_g1_plus", now) == "user-1:geomagnetic:kp_g1_plus:2026-03-17T12"


def test_cooldown_blocks_repeat_until_severity_escalates() -> None:
    previous = datetime(2026, 3, 17, 10, 5, tzinfo=timezone.utc)
    now = datetime(2026, 3, 17, 13, 0, tzinfo=timezone.utc)
    assert not can_emit_with_cooldown(
        previous_created_at=previous,
        previous_severity="watch",
        family="pressure",
        current_severity="watch",
        now_utc=now,
    )
    assert can_emit_with_cooldown(
        previous_created_at=previous,
        previous_severity="watch",
        family="pressure",
        current_severity="high",
        now_utc=now,
    )


def test_flare_class_rank_orders_bands_and_magnitude() -> None:
    assert flare_class_rank("X1.0") > flare_class_rank("M9.9")
    assert flare_class_rank("M5.0") > flare_class_rank("M1.2")
    assert flare_class_rank(None) == (-1, 0.0)


def test_gauge_helpers_reconstruct_previous_zone() -> None:
    current = 78.0
    previous = previous_gauge_value(current, 14)
    assert previous == 64.0
    assert gauge_zone(current) == "elevated"
    assert gauge_zone(84.0) == "high"
    assert gauge_zone(25.0) == "low"
