from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from services import space_weather_current


def test_fetch_current_space_weather_combines_swpc_rows_without_active_marker():
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    speed = Mock()
    speed.json.return_value = [{"proton_speed": 584, "time_tag": timestamp}]
    mag = Mock()
    mag.json.return_value = [{"bt": 8, "bz_gsm": 1, "time_tag": timestamp}]

    with patch.object(space_weather_current.requests, "get", side_effect=[speed, mag]):
        result = space_weather_current.fetch_current_space_weather(force=True)

    assert result["sw_speed_now_kms"] == 584.0
    assert result["bz_now"] == 1.0
    assert result["updated_at"] == timestamp


def test_fetch_current_space_weather_prefers_active_solar1_rows():
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    speed = Mock()
    speed.json.return_value = [
        {"time_tag": timestamp, "active": False, "source": "ACE", "proton_speed": 500},
        {"time_tag": timestamp, "active": True, "source": "SOLAR1", "proton_speed": 590},
    ]
    mag = Mock()
    mag.json.return_value = [
        {"time_tag": timestamp, "active": False, "source": "ACE", "bz_gsm": -2, "bt": 7},
        {"time_tag": timestamp, "active": True, "source": "SOLAR1", "bz_gsm": 4, "bt": 8},
    ]

    with patch.object(space_weather_current.requests, "get", side_effect=[speed, mag]):
        result = space_weather_current.fetch_current_space_weather(force=True)

    assert result["sw_speed_now_kms"] == 590.0
    assert result["bz_now"] == 4.0
    assert result["speed_spacecraft"] == "SOLAR1"
    assert result["mag_spacecraft"] == "SOLAR1"


def test_fetch_current_space_weather_uses_summary_when_rtsw_is_stale():
    stale = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    current = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    responses = []
    for payload in (
        [{"time_tag": stale, "active": True, "source": "SOLAR1", "proton_speed": 500}],
        [{"time_tag": current, "proton_speed": 610}],
        [{"time_tag": stale, "active": True, "source": "SOLAR1", "bz_gsm": -2}],
        [{"time_tag": current, "bz_gsm": 3, "bt": 7}],
    ):
        response = Mock()
        response.json.return_value = payload
        responses.append(response)

    with patch.object(space_weather_current.requests, "get", side_effect=responses):
        result = space_weather_current.fetch_current_space_weather(force=True)

    assert result["sw_speed_now_kms"] == 610.0
    assert result["bz_now"] == 3.0
    assert result["speed_source_url"] == space_weather_current._SPEED_FALLBACK_URL
    assert result["mag_source_url"] == space_weather_current._MAG_FALLBACK_URL
