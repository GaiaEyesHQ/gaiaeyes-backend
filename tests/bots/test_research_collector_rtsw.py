from bots.research_collector import research_collector


def test_latest_active_rtsw_row_uses_solar1_instead_of_newer_inactive_ace():
    rows = [
        {"time_tag": "2026-07-10T04:15:00", "active": False, "source": "ACE", "proton_speed": 500},
        {"time_tag": "2026-07-10T04:14:00", "active": True, "source": "SOLAR1", "proton_speed": 620},
    ]

    selected = research_collector._latest_active_rtsw_row(rows)

    assert selected["source"] == "SOLAR1"
    assert selected["proton_speed"] == 620


def test_latest_active_rtsw_row_still_accepts_legacy_table_shape():
    table = [
        ["time_tag", "speed", "density", "temperature"],
        ["2026-07-10T04:13:00", 610, 2.1, 400000],
        ["2026-07-10T04:14:00", 620, 2.0, 410000],
    ]

    selected = research_collector._latest_active_rtsw_row(table)

    assert selected["time_tag"] == "2026-07-10T04:14:00"
    assert selected["speed"] == 620
