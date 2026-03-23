from services.geomagnetic_context import (
    build_ulf_payload,
    map_ulf_confidence_label,
    map_ulf_context_label,
    normalize_ulf_context,
)


def test_map_ulf_context_label_simplifies_raw_backend_classes() -> None:
    assert map_ulf_context_label("Active (diffuse)") == "Active"
    assert map_ulf_context_label("Elevated (coherent)") == "Elevated"
    assert map_ulf_context_label("Strong (coherent)") == "Strong"
    assert map_ulf_context_label("Quiet") == "Quiet"


def test_map_ulf_confidence_label_buckets_scores() -> None:
    assert map_ulf_confidence_label(0.2) == "Low"
    assert map_ulf_confidence_label(0.5) == "Moderate"
    assert map_ulf_confidence_label(0.8) == "High"


def test_normalize_ulf_context_derives_provisional_and_station_count() -> None:
    context = normalize_ulf_context(
        {
            "context_class": "Elevated (coherent)",
            "confidence_score": 0.64,
            "regional_intensity": 78.95,
            "regional_coherence": 0.765,
            "regional_persistence": 51.88,
            "quality_flags": ["low_history"],
            "stations_used": ["BOU", "CMO"],
        }
    )

    assert context == {
        "label": "Elevated",
        "class_raw": "Elevated (coherent)",
        "confidence_score": 0.64,
        "confidence_label": "Moderate",
        "regional_intensity": 78.95,
        "regional_coherence": 0.765,
        "regional_persistence": 51.88,
        "quality_flags": ["low_history"],
        "is_provisional": True,
        "is_usable": True,
        "is_high_confidence": False,
        "station_count": 2,
        "missing_samples": False,
        "low_history": True,
        "ts_utc": None,
    }


def test_build_ulf_payload_returns_flat_and_nested_fields() -> None:
    payload = build_ulf_payload(
        {
            "context_class": "Strong (coherent)",
            "confidence_score": 0.82,
            "regional_intensity": 88.1,
            "regional_coherence": 0.91,
            "regional_persistence": 72.4,
            "quality_flags": ["missing_samples"],
            "stations_used": ["BOU", "CMO"],
            "ts_utc": "2026-03-22T12:00:00Z",
        }
    )

    assert payload["ulf_context_label"] == "Strong"
    assert payload["ulf_confidence_label"] == "High"
    assert payload["ulf_missing_samples"] is True
    assert payload["geomagnetic_context"]["ts_utc"] == "2026-03-22T12:00:00Z"
