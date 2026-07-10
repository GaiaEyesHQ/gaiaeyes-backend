from scripts import backfill_space_weather_hapi as backfill


def test_parse_hapi_csv_keeps_only_nominal_values():
    payload = """time_tag,speed,quality,source
2026-07-01T00:00:00Z,413.30,0,4
2026-07-01T00:01:00Z,500.00,1,4
2026-07-01T00:02:00Z,-1e30,0,4
"""

    rows = backfill.parse_hapi_csv(payload, "speed")

    assert len(rows) == 1
    record = next(iter(rows.values()))
    assert record == {"value": 413.3, "quality": 0, "source_code": "4"}
