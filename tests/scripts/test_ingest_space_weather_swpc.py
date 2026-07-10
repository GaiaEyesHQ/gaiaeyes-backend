from datetime import datetime, timedelta, timezone

from scripts import ingest_space_weather_swpc as ingest


def test_merge_metric_uses_only_swpc_active_spacecraft_rows():
    payload = [
        {
            "time_tag": "2026-07-10T03:55:00",
            "active": False,
            "source": "ACE",
            "proton_speed": 510.0,
            "overall_quality": 0,
        },
        {
            "time_tag": "2026-07-10T03:55:00",
            "active": True,
            "source": "SOLAR1",
            "proton_speed": 590.5,
            "overall_quality": 0,
        },
    ]
    records = ingest.rows_to_records(
        ingest.normalize_to_table(payload),
        {"ts": ["time_tag"]},
    )
    merged = {}

    ingest.merge_metric(
        records,
        ["proton_speed"],
        "sw_speed_kms",
        merged,
        active_only=True,
    )

    ts = datetime(2026, 7, 10, 3, 55, tzinfo=timezone.utc)
    assert merged[ts]["sw_speed_kms"] == 590.5
    assert merged[ts]["_provenance"]["sw_speed_kms"]["spacecraft"] == "SOLAR1"
    assert merged[ts]["_provenance"]["sw_speed_kms"]["active"] is True


def test_merge_metric_prefers_decimal_estimated_kp():
    payload = [
        {
            "time_tag": "2026-07-10T04:12:00",
            "kp_index": 2,
            "estimated_kp": 1.67,
            "kp": "2M",
        }
    ]
    records = ingest.rows_to_records(ingest.normalize_to_table(payload), {"ts": ["time_tag"]})
    merged = {}

    ingest.merge_metric(records, ["estimated_kp", "kp_index", "kp"], "kp_index", merged)

    ts = datetime(2026, 7, 10, 4, 12, tzinfo=timezone.utc)
    assert merged[ts]["kp_index"] == 1.67


def test_rtsw_urls_are_primary_and_legacy_solar_wind_products_are_not_used():
    assert ingest.URLS_LIST["kp"][0].endswith("/json/planetary_k_index_1m.json")
    assert ingest.URLS_LIST["speed"][0].endswith("/json/rtsw/rtsw_wind_1m.json")
    assert ingest.URLS_LIST["mag"][0].endswith("/json/rtsw/rtsw_mag_1m.json")
    assert not any("products/solar-wind" in url for url in ingest.URLS_LIST["speed"])
    assert not any("products/solar-wind" in url for url in ingest.URLS_LIST["mag"])


def test_latest_table_timestamp_exposes_frozen_feed():
    old = datetime.now(timezone.utc) - timedelta(days=2)
    recent = datetime.now(timezone.utc)
    table = [
        ["time_tag", "active", "source", "proton_speed"],
        [recent.isoformat(), False, "ACE", 510.0],
        [old.isoformat(), True, "SOLAR1", 500.0],
    ]

    assert ingest.latest_table_timestamp(table) == recent
    assert ingest.latest_table_timestamp(table, active_only=True) == old
    assert ingest.latest_table_timestamp(table, active_only=True) < datetime.now(timezone.utc) - timedelta(minutes=90)
