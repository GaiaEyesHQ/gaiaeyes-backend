from __future__ import annotations

import sys
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.forecast_outlook import (  # noqa: E402
    LOCAL_FORECAST_DAYS,
    POLLEN_FORECAST_DAYS,
    build_daily_outlook,
    build_location_key,
    build_user_outlook_payload,
    build_window_outlook,
    ensure_local_forecast_daily,
    parse_swpc_range_forecast,
    parse_swpc_three_day_forecast,
    serialize_local_forecast_rows,
    serialize_space_forecast_rows,
    summarize_local_forecast_days,
)
from services.external import nws  # noqa: E402


class ForecastOutlookTests(unittest.TestCase):
    def test_parse_swpc_three_day_forecast_extracts_daily_fields(self) -> None:
        text = """
:Product: 3-Day Forecast
:Issued: 2026 Mar 18 2200 UTC
#
A. NOAA Geomagnetic Activity Observation and Forecast
NOAA Kp index breakdown Mar 19-Mar 21 2026

               Mar 19        Mar 20        Mar 21
00-03UT      3.67 (G0)     4.67 (G0)     5.33 (G1)
03-06UT      4.00 (G0)     5.00 (G1)     5.67 (G1)

Rationale: G1 storming is possible on 21 Mar due to recurrent high speed stream effects.

B. NOAA Solar Radiation Activity Observation and Forecast
Solar Radiation Storm Forecast for Mar 19-Mar 21 2026

               Mar 19    Mar 20    Mar 21
S1 or greater    5%       10%       15%

Rationale: No significant solar radiation storms are expected.

C. NOAA Radio Blackout Activity and Forecast
Radio Blackout Forecast for Mar 19-Mar 21 2026

               Mar 19    Mar 20    Mar 21
R1-R2           15%       20%       35%
R3 or greater    1%        1%        5%

Rationale: Active regions may keep a modest flare chance in the outlook.
"""

        rows = parse_swpc_three_day_forecast(
            text,
            source_product_ts=datetime(2026, 3, 18, 22, 5, tzinfo=UTC),
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["forecast_day"], date(2026, 3, 19))
        self.assertEqual(rows[2]["g_scale_max"], "G1")
        self.assertAlmostEqual(rows[2]["kp_max_forecast"], 5.67, places=2)
        self.assertEqual(rows[1]["s1_or_greater_pct"], 10.0)
        self.assertEqual(rows[2]["r1_r2_pct"], 35.0)
        self.assertTrue(rows[2]["solar_wind_watch"])
        self.assertTrue(rows[2]["flare_watch"])
        self.assertEqual(rows[2]["geomagnetic_severity_bucket"], "watch")
        self.assertEqual(rows[2]["radio_severity_bucket"], "watch")

    def test_parse_swpc_three_day_forecast_handles_compact_live_style_text(self) -> None:
        text = (
            ":Product: 3-Day Forecast :Issued: 2026 Mar 19 0030 UTC "
            "A. NOAA Geomagnetic Activity Observation and Forecast "
            "The greatest expected 3 hr Kp for Mar 19-Mar 21 2026 is 6.33 (NOAA Scale G2). "
            "NOAA Kp index breakdown Mar 19-Mar 21 2026 Mar 19 Mar 20 Mar 21 "
            "00-03UT 1.67 6.33 (G2) 4.33 03-06UT 2.00 6.00 (G2) 6.33 (G2) "
            "Rationale: G1-G2 storms are expected due to CME arrivals and a sector boundary crossing. "
            "B. NOAA Solar Radiation Activity Observation and Forecast "
            "Solar Radiation Storm Forecast for Mar 19-Mar 21 2026 Mar 19 Mar 20 Mar 21 "
            "S1 or greater 10% 10% 10% Rationale: There is a slight chance for S1 storms. "
            "C. NOAA Radio Blackout Activity and Forecast "
            "Radio Blackout Forecast for Mar 19-Mar 21 2026 Mar 19 Mar 20 Mar 21 "
            "R1-R2 35% 35% 35% R3 or greater 10% 10% 10% "
            "Rationale: There is a chance for R1-R2 blackouts with a slight chance for R3 events."
        )

        rows = parse_swpc_three_day_forecast(
            text,
            source_product_ts=datetime(2026, 3, 19, 0, 35, tzinfo=UTC),
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["forecast_day"], date(2026, 3, 19))
        self.assertEqual(rows[0]["kp_max_forecast"], 2.0)
        self.assertEqual(rows[1]["kp_max_forecast"], 6.33)
        self.assertEqual(rows[2]["kp_max_forecast"], 6.33)
        self.assertEqual(rows[0]["s1_or_greater_pct"], 10.0)
        self.assertEqual(rows[2]["r3_or_greater_pct"], 10.0)
        self.assertTrue(rows[0]["cme_watch"])
        self.assertEqual(rows[1]["geomagnetic_severity_bucket"], "watch")

    def test_parse_swpc_range_forecast_builds_seven_day_window_from_weekly(self) -> None:
        text = """
:Product: Weekly Highlights and Forecasts
:Issued: 2026 Mar 23 0245 UTC
Forecast of Solar and Geomagnetic Activity
23 March - 18 April 2026

Solar activity is expected to be at low levels with a varying chance
for M-class (R1-R2/Minor-Moderate) flares through 18 Apr.

Geomagnetic field activity is expected to reach G1-G2
(Minor-Moderate) geomagnetic storm levels on 23 Mar due to negative
polarity CH HSS influences. Periods of G1 (Minor) storming are
likely on 03-04 Apr in response to negative polarity CH HSS
influences.
"""

        rows = parse_swpc_range_forecast(
            text,
            source_product_ts=datetime(2026, 3, 23, 2, 50, tzinfo=UTC),
            src="noaa-swpc:weekly",
        )

        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["forecast_day"], date(2026, 3, 23))
        self.assertEqual(rows[0]["g_scale_max"], "G2")
        self.assertTrue(rows[0]["solar_wind_watch"])
        self.assertTrue(rows[0]["flare_watch"])
        self.assertEqual(rows[1]["g_scale_max"], "G0")

    def test_parse_swpc_range_forecast_builds_seven_day_window_from_advisory(self) -> None:
        text = """
:Product: Advisory Outlook advisory-outlook.txt
:Issued: 2026 Mar 23 0250 UTC
**** SPACE WEATHER OUTLOOK ****
Outlook For March 23-29

-G1-G2 (Minor-Moderate) storm periods are expected on 23 Mar due to CH HSS influences.
"""

        rows = parse_swpc_range_forecast(
            text,
            source_product_ts=datetime(2026, 3, 23, 2, 51, tzinfo=UTC),
            src="noaa-swpc:advisory-outlook",
        )

        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["forecast_day"], date(2026, 3, 23))
        self.assertEqual(rows[0]["g_scale_max"], "G2")
        self.assertTrue(rows[0]["solar_wind_watch"])
        self.assertEqual(rows[1]["g_scale_max"], "G0")

    def test_summarize_local_forecast_days_aggregates_hourly_periods(self) -> None:
        hourly_payload = {
            "properties": {
                "generatedAt": "2026-03-18T10:00:00Z",
                "periods": [
                    {
                        "startTime": "2026-03-18T11:00:00-05:00",
                        "temperature": 64,
                        "temperatureUnit": "F",
                        "relativeHumidity": {"value": 60},
                        "probabilityOfPrecipitation": {"value": 20},
                        "windSpeed": "5 to 10 mph",
                        "windGust": "18 mph",
                        "shortForecast": "Mostly Cloudy",
                    },
                    {
                        "startTime": "2026-03-18T17:00:00-05:00",
                        "temperature": 72,
                        "temperatureUnit": "F",
                        "relativeHumidity": {"value": 52},
                        "probabilityOfPrecipitation": {"value": 35},
                        "windSpeed": "10 mph",
                        "windGust": "20 mph",
                        "shortForecast": "Mostly Cloudy",
                    },
                    {
                        "startTime": "2026-03-19T11:00:00-05:00",
                        "temperature": 68,
                        "temperatureUnit": "F",
                        "relativeHumidity": {"value": 58},
                        "probabilityOfPrecipitation": {"value": 40},
                        "windSpeed": "8 mph",
                        "windGust": "15 mph",
                        "shortForecast": "Chance Showers",
                    },
                    {
                        "startTime": "2026-03-19T17:00:00-05:00",
                        "temperature": 78,
                        "temperatureUnit": "F",
                        "relativeHumidity": {"value": 48},
                        "probabilityOfPrecipitation": {"value": 55},
                        "windSpeed": "12 mph",
                        "windGust": "25 mph",
                        "shortForecast": "Chance Showers",
                    },
                    {
                        "startTime": "2026-03-20T11:00:00-05:00",
                        "temperature": 70,
                        "temperatureUnit": "F",
                        "relativeHumidity": {"value": 62},
                        "probabilityOfPrecipitation": {"value": 10},
                        "windSpeed": "6 mph",
                        "windGust": "14 mph",
                        "shortForecast": "Sunny",
                    },
                    {
                        "startTime": "2026-03-20T17:00:00-05:00",
                        "temperature": 82,
                        "temperatureUnit": "F",
                        "relativeHumidity": {"value": 44},
                        "probabilityOfPrecipitation": {"value": 15},
                        "windSpeed": "9 mph",
                        "windGust": "18 mph",
                        "shortForecast": "Sunny",
                    },
                ]
            }
        }
        grid_payload = {
            "properties": {
                "barometricPressure": {
                    "values": [
                        {"validTime": "2026-03-18T00:00:00+00:00/PT12H", "value": 101300},
                        {"validTime": "2026-03-19T00:00:00+00:00/PT12H", "value": 100800},
                        {"validTime": "2026-03-20T00:00:00+00:00/PT12H", "value": 101600},
                    ]
                }
            }
        }
        allergen_payload = {
            "dailyInfo": [
                {
                    "date": {"year": 2026, "month": 3, "day": 18},
                    "pollenTypeInfo": [
                        {"code": "TREE", "displayName": "Tree", "indexInfo": {"value": 4, "category": "HIGH"}},
                        {"code": "GRASS", "displayName": "Grass", "indexInfo": {"value": 2, "category": "LOW"}},
                        {"code": "WEED", "displayName": "Weed", "indexInfo": {"value": 3, "category": "MODERATE"}},
                    ],
                },
                {
                    "date": {"year": 2026, "month": 3, "day": 19},
                    "pollenTypeInfo": [
                        {"code": "TREE", "displayName": "Tree", "indexInfo": {"value": 5, "category": "VERY_HIGH"}},
                        {"code": "GRASS", "displayName": "Grass", "indexInfo": {"value": 2, "category": "LOW"}},
                    ],
                },
                {
                    "date": {"year": 2026, "month": 3, "day": 20},
                    "pollenTypeInfo": [
                        {"code": "GRASS", "displayName": "Grass", "indexInfo": {"value": 4, "category": "HIGH"}},
                    ],
                },
            ]
        }

        rows = summarize_local_forecast_days(
            hourly_payload,
            grid_payload,
            allergen_payload=allergen_payload,
            location_key="zip:78701",
            zip_code="78701",
            lat=30.2672,
            lon=-97.7431,
            now=datetime(2026, 3, 18, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["day"], date(2026, 3, 18))
        self.assertAlmostEqual(rows[0]["temp_high_c"], 22.2, places=1)
        self.assertAlmostEqual(rows[0]["temp_low_c"], 17.8, places=1)
        self.assertEqual(rows[0]["condition_code"], "mostly-cloudy")
        self.assertEqual(rows[1]["condition_summary"], "Chance Showers")
        self.assertAlmostEqual(rows[1]["temp_delta_from_prior_day_c"], 2.8, places=1)
        self.assertAlmostEqual(rows[2]["pressure_delta_from_prior_day_hpa"], 8.0, places=1)
        self.assertGreater(rows[1]["wind_gust"], rows[1]["wind_speed"])
        self.assertEqual(rows[0]["pollen_overall_level"], "high")
        self.assertEqual(rows[1]["pollen_primary_type"], "tree")
        self.assertEqual(rows[2]["pollen_grass_level"], "high")

    def test_build_window_outlook_prioritizes_pattern_linked_driver(self) -> None:
        merged_rows = [
            {
                "day": date(2026, 3, 19),
                "pressure_delta_from_prior_day_hpa": -7.4,
                "temp_delta_from_prior_day_c": 2.0,
                "kp_max_forecast": 5.3,
                "g_scale_max": "G1",
            },
            {
                "day": date(2026, 3, 20),
                "pressure_delta_from_prior_day_hpa": -3.0,
                "temp_delta_from_prior_day_c": 1.5,
                "kp_max_forecast": 4.0,
                "g_scale_max": "G0",
            },
        ]
        pattern_rows = [
            {
                "signal_key": "pressure_swing_exposed",
                "outcome_key": "pain_flare_day",
                "confidence": "Strong",
                "relative_lift": 2.4,
                "lag_hours": 24,
            },
            {
                "signal_key": "kp_g1_plus_exposed",
                "outcome_key": "poor_sleep_day",
                "confidence": "Moderate",
                "relative_lift": 1.7,
                "lag_hours": 24,
            },
        ]
        gauges = {"pain": 78, "sleep": 61}

        payload = build_window_outlook(
            merged_rows,
            pattern_rows=pattern_rows,
            gauges=gauges,
            window_hours=24,
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["likely_elevated_domains"][0]["key"], "pain")
        self.assertEqual(payload["top_drivers"][0]["key"], "pressure")
        self.assertIn("pressure may swing", payload["summary"].lower())
        self.assertIn("pacing and hydration", payload["support_line"].lower())
        self.assertIn("pain", payload["likely_elevated_domains"][0]["explanation"].lower())
        self.assertEqual(payload["voice_semantic"]["kind"], "user_outlook_window")
        self.assertIn(
            "pressure may swing",
            payload["voice_semantic"]["interpretation"]["header_summary"].lower(),
        )
        self.assertIn(
            "pain",
            payload["voice_semantic"]["interpretation"]["domains_summary"].lower(),
        )

    def test_build_window_outlook_surfaces_allergen_driver_when_present(self) -> None:
        merged_rows = [
            {
                "day": date(2026, 3, 19),
                "pollen_overall_level": "high",
                "pollen_overall_index": 4.0,
                "pollen_primary_type": "tree",
            },
            {
                "day": date(2026, 3, 20),
                "pollen_overall_level": "moderate",
                "pollen_overall_index": 3.0,
                "pollen_primary_type": "weed",
            },
        ]

        payload = build_window_outlook(
            merged_rows,
            pattern_rows=[],
            gauges={},
            window_hours=24,
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["top_drivers"][0]["key"], "allergens")
        self.assertEqual(payload["top_drivers"][0]["label"], "Tree pollen")
        self.assertIn("tree pollen", payload["summary"].lower())
        self.assertIn("filters", payload["support_line"].lower())
        self.assertEqual(payload["voice_semantic"]["kind"], "user_outlook_window")
        self.assertIn(
            "tree pollen",
            payload["voice_semantic"]["interpretation"]["header_summary"].lower(),
        )

    def test_build_window_outlook_surfaces_humidity_driver_when_extreme(self) -> None:
        merged_rows = [
            {
                "day": date(2026, 3, 19),
                "humidity_avg": 82.0,
            },
            {
                "day": date(2026, 3, 20),
                "humidity_avg": 76.0,
            },
        ]

        payload = build_window_outlook(
            merged_rows,
            pattern_rows=[],
            gauges={},
            window_hours=24,
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["top_drivers"][0]["key"], "humidity")
        self.assertEqual(payload["top_drivers"][0]["label"], "Humidity")
        self.assertIn("humidity looks muggier", payload["summary"].lower())
        self.assertIn("hydration", payload["support_line"].lower())

    def test_build_daily_outlook_returns_weather_style_days(self) -> None:
        merged_rows = [
            {
                "day": date(2026, 3, 19),
                "humidity_avg": 82.0,
            },
            {
                "day": date(2026, 3, 20),
                "pollen_overall_level": "high",
                "pollen_overall_index": 4.0,
                "pollen_primary_type": "tree",
            },
        ]

        with patch("services.forecast_outlook._app_today", return_value=date(2026, 3, 18)):
            payload = build_daily_outlook(
                merged_rows,
                pattern_rows=[],
                gauges={},
                days=7,
            )

        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["day"], "2026-03-19")
        self.assertEqual(payload[0]["top_drivers"][0]["key"], "humidity")
        self.assertEqual(payload[1]["top_drivers"][0]["key"], "allergens")
        self.assertTrue(payload[0]["label"])
        self.assertIsNone(payload[0]["summary"])
        self.assertIsNone(payload[0]["voice_semantic"]["interpretation"]["header_summary"])
        self.assertIsNone(payload[0]["support_line"])

    def test_build_daily_outlook_uses_type_specific_pollen_when_overall_level_is_missing(self) -> None:
        merged_rows = [
            {
                "day": date(2026, 3, 19),
                "pollen_primary_type": "grass",
                "pollen_grass_level": "moderate",
                "pollen_grass_index": 3.1,
            },
        ]

        with patch("services.forecast_outlook._app_today", return_value=date(2026, 3, 18)):
            payload = build_daily_outlook(
                merged_rows,
                pattern_rows=[],
                gauges={},
                days=7,
            )

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["top_drivers"][0]["key"], "allergens")
        self.assertEqual(payload[0]["top_drivers"][0]["label"], "Grass pollen")

    def test_build_daily_outlook_keeps_space_weather_visible_with_local_drivers(self) -> None:
        merged_rows = [
            {
                "day": date(2026, 3, 19),
                "pressure_delta_from_prior_day_hpa": 8.0,
                "temp_delta_from_prior_day_c": 5.0,
                "humidity_avg": 82.0,
                "aqi_forecast": 88,
                "pollen_overall_level": "high",
                "pollen_overall_index": 4.0,
                "pollen_primary_type": "tree",
                "kp_max_forecast": 5.0,
                "g_scale_max": "G1",
                "cme_watch": True,
                "geomagnetic_severity_bucket": "watch",
            },
        ]

        with patch("services.forecast_outlook._app_today", return_value=date(2026, 3, 18)):
            payload = build_daily_outlook(
                merged_rows,
                pattern_rows=[],
                gauges={},
                days=7,
            )

        self.assertEqual(len(payload), 1)
        keys = [driver["key"] for driver in payload[0]["top_drivers"]]
        self.assertTrue(any(key in {"kp", "cme"} for key in keys))
        self.assertIsNone(payload[0]["summary"])
        self.assertIsNone(payload[0]["voice_semantic"]["interpretation"]["header_summary"])

    def test_build_daily_outlook_uses_app_day_when_filtering_future_rows(self) -> None:
        merged_rows = [
            {
                "day": date(2026, 4, 21),
                "humidity_avg": 82.0,
            },
            {
                "day": date(2026, 4, 22),
                "pollen_overall_level": "high",
                "pollen_overall_index": 4.0,
                "pollen_primary_type": "tree",
            },
        ]

        with patch("services.forecast_outlook._app_today", return_value=date(2026, 4, 21)):
            payload = build_daily_outlook(
                merged_rows,
                pattern_rows=[],
                gauges={},
                days=7,
            )

        self.assertEqual([item["day"] for item in payload], ["2026-04-22"])
        self.assertEqual(payload[0]["label"], "Tomorrow")

    def test_build_daily_outlook_keeps_local_driver_visible_when_space_signals_dominate(self) -> None:
        merged_rows = [
            {
                "day": date(2026, 3, 19),
                "humidity_avg": 70.0,
                "kp_max_forecast": 5.0,
                "g_scale_max": "G1",
                "cme_watch": True,
                "flare_watch": True,
            },
        ]

        with patch("services.forecast_outlook._app_today", return_value=date(2026, 3, 18)):
            payload = build_daily_outlook(
                merged_rows,
                pattern_rows=[
                    {
                        "signal_key": "kp_g1_plus_exposed",
                        "outcome_key": "fatigue_day",
                        "confidence": "strong",
                        "relative_lift": 3.0,
                        "lag_hours": 24,
                    }
                ],
                gauges={"energy": 72},
                days=7,
            )

        keys = [driver["key"] for driver in payload[0]["top_drivers"]]
        self.assertIn("kp", keys)
        self.assertIn("humidity", keys)
        self.assertTrue(any(key in {"cme", "flare"} for key in keys))

    def test_build_window_outlook_keeps_domain_drivers_within_visible_driver_stack(self) -> None:
        merged_rows = [
            {
                "day": date(2026, 3, 19),
                "humidity_avg": 88.0,
                "kp_max_forecast": 5.0,
                "g_scale_max": "G1",
                "pollen_overall_level": "moderate",
                "pollen_overall_index": 3.0,
                "pollen_primary_type": "grass",
                "temp_delta_from_prior_day_c": 2.1,
            },
            {
                "day": date(2026, 3, 20),
                "humidity_avg": 82.0,
                "kp_max_forecast": 4.0,
                "g_scale_max": "G0",
                "pollen_overall_level": "moderate",
                "pollen_overall_index": 2.8,
                "pollen_primary_type": "grass",
                "temp_delta_from_prior_day_c": 1.8,
            },
        ]

        pattern_rows = [
            {
                "signal_key": "humidity_extreme_exposed",
                "outcome_key": "fatigue_day",
                "confidence": "Strong",
                "relative_lift": 2.4,
                "lag_hours": 24,
            },
            {
                "signal_key": "kp_g1_plus_exposed",
                "outcome_key": "poor_sleep_day",
                "confidence": "Moderate",
                "relative_lift": 1.8,
                "lag_hours": 24,
            },
            {
                "signal_key": "pollen_overall_exposed",
                "outcome_key": "pain_flare_day",
                "confidence": "Moderate",
                "relative_lift": 1.6,
                "lag_hours": 24,
            },
            {
                "signal_key": "temp_swing_exposed",
                "outcome_key": "focus_fog_day",
                "confidence": "Weak",
                "relative_lift": 1.1,
                "lag_hours": 24,
            },
        ]

        payload = build_window_outlook(
            merged_rows,
            pattern_rows=pattern_rows,
            gauges={"energy": 52, "sleep": 41, "pain": 39, "focus": 30},
            window_hours=24,
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        visible_driver_keys = {item["key"] for item in payload["top_drivers"]}
        self.assertTrue(visible_driver_keys)
        self.assertTrue(payload["likely_elevated_domains"])
        self.assertTrue(
            all(
                str(item.get("top_driver_key") or "") in visible_driver_keys
                for item in payload["likely_elevated_domains"]
            )
        )

    def test_forecast_row_serializers_emit_json_safe_shapes(self) -> None:
        local_rows = [
            {
                "location_key": "zip:78754",
                "day": date(2026, 3, 19),
                "issued_at": datetime(2026, 3, 19, 3, 0, tzinfo=UTC),
                "temp_high_c": 29.4,
                "temp_low_c": 11.1,
                "pressure_hpa": None,
                "updated_at": datetime(2026, 3, 19, 3, 5, tzinfo=UTC),
            }
        ]
        space_rows = [
            {
                "forecast_day": date(2026, 3, 19),
                "issued_at": datetime(2026, 3, 19, 0, 30, tzinfo=UTC),
                "source_product_ts": datetime(2026, 3, 19, 0, 35, tzinfo=UTC),
                "kp_max_forecast": 6.33,
                "g_scale_max": "G2",
                "flare_watch": True,
                "cme_watch": False,
                "solar_wind_watch": True,
                "updated_at": datetime(2026, 3, 19, 0, 40, tzinfo=UTC),
            }
        ]

        local_payload = serialize_local_forecast_rows(local_rows)
        space_payload = serialize_space_forecast_rows(space_rows)

        self.assertEqual(local_payload[0]["day"], "2026-03-19")
        self.assertIsNone(local_payload[0]["pressure_hpa"])
        self.assertIsNone(local_payload[0]["pollen_overall_level"])
        self.assertEqual(space_payload[0]["forecast_day"], "2026-03-19")
        self.assertEqual(space_payload[0]["g_scale_max"], "G2")
        self.assertTrue(space_payload[0]["flare_watch"])
        self.assertFalse(space_payload[0]["cme_watch"])

    def test_build_location_key_prefers_geo_when_requested(self) -> None:
        self.assertEqual(
            build_location_key("78209", 30.2672, -97.7431, prefer_geo=True),
            "geo:30.267,-97.743",
        )


class ForecastOutlookAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_user_outlook_payload_prefers_geo_cache_for_gps_profiles(self) -> None:
        conn = object()
        with (
            patch(
                "services.forecast_outlook.fetch_user_location_context",
                AsyncMock(
                    return_value={
                        "zip": "78209",
                        "lat": 30.2672,
                        "lon": -97.7431,
                        "use_gps": True,
                        "local_insights_enabled": True,
                    }
                ),
            ),
            patch(
                "services.forecast_outlook.ensure_local_forecast_daily",
                AsyncMock(return_value=[]),
            ) as ensure_local,
            patch("services.forecast_outlook.ensure_space_forecast_daily", AsyncMock(return_value=[])),
            patch("services.forecast_outlook.fetch_best_pattern_rows", AsyncMock(return_value=[])),
            patch("services.forecast_outlook.fetch_latest_gauges", AsyncMock(return_value={})),
        ):
            payload = await build_user_outlook_payload(conn, "user-123")

        self.assertTrue(payload["forecast_data_ready"]["location_found"])
        kwargs = ensure_local.await_args.kwargs
        self.assertEqual(kwargs["zip_code"], "78209")
        self.assertEqual(kwargs["lat"], 30.2672)
        self.assertEqual(kwargs["lon"], -97.7431)
        self.assertTrue(kwargs["prefer_geo"])

    async def test_ensure_local_forecast_daily_refreshes_fresh_rows_when_pollen_is_missing(self) -> None:
        now = datetime.now(UTC)
        existing = [
            {
                "day": date(2026, 4, 21) + timedelta(days=index),
                "updated_at": now,
                "pollen_overall_level": None,
            }
            for index in range(LOCAL_FORECAST_DAYS)
        ]
        refreshed = [
            {
                "day": date(2026, 4, 21) + timedelta(days=index),
                "updated_at": now,
                "pollen_overall_level": "moderate",
            }
            for index in range(LOCAL_FORECAST_DAYS)
        ]

        class _Conn:
            async def commit(self) -> None:
                return None

        with (
            patch("services.forecast_outlook._fetch_local_forecast_rows", AsyncMock(side_effect=[existing, refreshed])),
            patch("services.forecast_outlook.summarize_local_forecast_days", return_value=refreshed),
            patch("services.forecast_outlook._upsert_local_forecast_rows", AsyncMock()) as upsert_rows,
            patch.object(nws, "forecast_hourly_by_latlon", AsyncMock(return_value={})),
            patch.object(nws, "gridpoints_by_latlon", AsyncMock(return_value={})),
            patch("services.forecast_outlook._fetch_local_pollen_forecast", AsyncMock(return_value={})) as fetch_pollen,
        ):
            payload = await ensure_local_forecast_daily(
                _Conn(),
                zip_code="78209",
                lat=29.49,
                lon=-98.47,
                days=LOCAL_FORECAST_DAYS,
            )

        upsert_rows.assert_awaited_once()
        fetch_pollen.assert_awaited_once_with("78209", 29.49, -98.47, days=POLLEN_FORECAST_DAYS)
        self.assertEqual(payload[0]["pollen_overall_level"], "moderate")

    async def test_ensure_local_forecast_daily_keeps_type_specific_pollen_rows_without_refresh(self) -> None:
        now = datetime.now(UTC)
        existing = [
            {
                "day": date(2026, 4, 21) + timedelta(days=index),
                "updated_at": now,
                "pollen_overall_level": None,
                "pollen_primary_type": "grass",
                "pollen_grass_level": "low",
                "pollen_source": "google-pollen:forecast",
            }
            for index in range(LOCAL_FORECAST_DAYS)
        ]

        class _Conn:
            async def commit(self) -> None:
                return None

        with (
            patch("services.forecast_outlook._fetch_local_forecast_rows", AsyncMock(return_value=existing)),
            patch("services.forecast_outlook.summarize_local_forecast_days", return_value=[]),
            patch("services.forecast_outlook._upsert_local_forecast_rows", AsyncMock()) as upsert_rows,
            patch.object(nws, "forecast_hourly_by_latlon", AsyncMock(return_value={})) as fetch_hourly,
            patch.object(nws, "gridpoints_by_latlon", AsyncMock(return_value={})) as fetch_grid,
            patch("services.forecast_outlook._fetch_local_pollen_forecast", AsyncMock(return_value={})) as fetch_pollen,
        ):
            payload = await ensure_local_forecast_daily(
                _Conn(),
                zip_code="78209",
                lat=29.49,
                lon=-98.47,
                days=LOCAL_FORECAST_DAYS,
            )

        upsert_rows.assert_not_awaited()
        fetch_hourly.assert_not_awaited()
        fetch_grid.assert_not_awaited()
        fetch_pollen.assert_not_awaited()
        self.assertEqual(payload, existing)


if __name__ == "__main__":
    unittest.main()
