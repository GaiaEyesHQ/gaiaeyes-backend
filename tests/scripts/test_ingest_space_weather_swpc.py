from datetime import datetime, timedelta, timezone

from scripts import ingest_space_weather_swpc as ingest


def test_merge_metric_uses_only_swpc_active_spacecraft_rows():
    payload = [
        {
            "time_tag": "2026-07-10T03:55:00",
            "active": False,
            "source": "ACE",
            "proton_density": 3.1,
            "proton_speed": 510.0,
            "overall_quality": 0,
        },
        {
            "time_tag": "2026-07-10T03:55:00",
            "active": True,
            "source": "SOLAR1",
            "proton_density": 4.7,
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
    ingest.merge_metric(
        records,
        ["proton_density"],
        "sw_density_cm3",
        merged,
        active_only=True,
    )

    ts = datetime(2026, 7, 10, 3, 55, tzinfo=timezone.utc)
    assert merged[ts]["sw_speed_kms"] == 590.5
    assert merged[ts]["sw_density_cm3"] == 4.7
    assert merged[ts]["_provenance"]["sw_speed_kms"]["spacecraft"] == "SOLAR1"
    assert merged[ts]["_provenance"]["sw_density_cm3"]["spacecraft"] == "SOLAR1"
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


def test_merge_metric_reads_official_three_hour_kp_product():
    payload = [
        ["time_tag", "Kp", "a_running", "station_count"],
        ["2026-08-06 03:00:00.000", "1.33", "3", "8"],
    ]
    records = ingest.rows_to_records(payload, {"ts": ["time_tag"]})
    merged = {}

    ingest.merge_metric(records, ["estimated_kp", "kp_est", "kp_index", "kp"], "kp_index", merged)

    ts = datetime(2026, 8, 6, 3, 0, tzinfo=timezone.utc)
    assert merged[ts]["kp_index"] == 1.33


def test_merge_metric_drops_noaa_missing_speed_sentinel():
    payload = [
        {
            "time_tag": "2026-08-04T01:03:00",
            "active": True,
            "source": "SOLAR1",
            "proton_speed": -9999,
        }
    ]
    records = ingest.rows_to_records(ingest.normalize_to_table(payload), {"ts": ["time_tag"]})
    merged = {}

    ingest.merge_metric(records, ["proton_speed"], "sw_speed_kms", merged, active_only=True)

    ts = datetime(2026, 8, 4, 1, 3, tzinfo=timezone.utc)
    assert "sw_speed_kms" not in merged[ts]


def test_official_kp_and_rtsw_urls_are_primary():
    assert ingest.URLS_LIST["kp"][0].endswith("/products/noaa-planetary-k-index.json")
    assert ingest.URLS_LIST["kp"][1].endswith("/json/planetary_k_index_1m.json")
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
