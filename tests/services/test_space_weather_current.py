from unittest.mock import Mock, patch

from services import space_weather_current


def test_fetch_current_space_weather_combines_swpc_summary_rows():
    speed = Mock()
    speed.json.return_value = [{"proton_speed": 584, "time_tag": "2026-07-10T03:18:00Z"}]
    mag = Mock()
    mag.json.return_value = [{"bt": 8, "bz_gsm": 1, "time_tag": "2026-07-10T03:18:00Z"}]

    with patch.object(space_weather_current.requests, "get", side_effect=[speed, mag]):
        result = space_weather_current.fetch_current_space_weather(force=True)

    assert result["sw_speed_now_kms"] == 584.0
    assert result["bz_now"] == 1.0
    assert result["updated_at"] == "2026-07-10T03:18:00+00:00"
