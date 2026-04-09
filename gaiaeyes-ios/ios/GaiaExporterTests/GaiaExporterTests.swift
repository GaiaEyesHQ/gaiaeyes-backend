//
//  GaiaExporterTests.swift
//  GaiaExporterTests
//
//  Created by Jennifer O'Brien on 8/24/25.
//

import Foundation
import Testing
@testable import GaiaEyes

struct SymptomEnvelopeTests {

    @Test
    func decodesSymptomEnvelope() throws {
        let payload = """
        {
            "ok": true,
            "data": [
                {
                    "symptom_code": "nerve_pain",
                    "ts_utc": "2025-01-01T00:00:00Z",
                    "severity": 3,
                    "free_text": "baseline"
                }
            ]
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let envelope = try decoder.decode(Envelope<[SymptomEventToday]>.self, from: payload)
        let data = envelope.payload ?? []

        #expect(envelope.ok == true)
        #expect(data.count == 1)
        #expect(data.first?.symptomCode == "nerve_pain")
        #expect(data.first?.severity == 3)
        #expect(data.first?.freeText == "baseline")
    }

    @Test
    func normalizesQueuedEventCodes() {
        let event = SymptomQueuedEvent(symptomCode: "nerve pain")
        #expect(event.symptomCode == "NERVE_PAIN")
        #expect(event.severity == 5)
}

    @Test
    func fallsBackToSnapshotPayload() throws {
        let payload = """
        {
            "ok": false,
            "data": null,
            "snapshot": [
                {
                    "symptom_code": "fatigue",
                    "ts_utc": "2025-02-01T00:00:00Z"
                }
            ],
            "cancellations": ["abc", "def"]
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let envelope = try decoder.decode(Envelope<[SymptomEventToday]>.self, from: payload)
        let data = envelope.payload ?? []

        #expect(envelope.ok == false)
        #expect(data.count == 1)
        #expect(envelope.cancellations?.count == 2)
        #expect(data.first?.symptomCode == "fatigue")
    }

    @Test
    func decodesCurrentSymptomsSnapshot() throws {
        let payload = """
        {
            "ok": true,
            "data": {
                "generated_at": "2026-03-23T12:00:00Z",
                "window_hours": 12,
                "summary": {
                    "active_count": 1,
                    "new_count": 0,
                    "ongoing_count": 1,
                    "improving_count": 0,
                    "worse_count": 0,
                    "last_updated_at": "2026-03-23T11:45:00Z",
                    "follow_up_available": true
                },
                "items": [
                    {
                        "id": "ep-1",
                        "symptom_code": "HEADACHE",
                        "label": "Headache",
                        "severity": 7,
                        "original_severity": 8,
                        "logged_at": "2026-03-23T09:00:00Z",
                        "last_interaction_at": "2026-03-23T11:45:00Z",
                        "current_state": "ongoing",
                        "note_preview": "Worse this afternoon",
                        "note_count": 1,
                        "likely_drivers": [
                            {
                                "key": "pressure",
                                "label": "Pressure swings",
                                "severity": "watch",
                                "state": "watch",
                                "display": "6.8 hPa swing",
                                "relation": "Pressure often matches your headache pattern.",
                                "related_symptoms": ["Headache"],
                                "confidence": "Moderate",
                                "pattern_hint": "Pressure often matches your headache pattern."
                            }
                        ],
                        "pattern_hint": {
                            "id": "pressure_swing_exposed|headache_day|0",
                            "signal_key": "pressure_swing_exposed",
                            "signal": "Pressure swings",
                            "outcome_key": "headache_day",
                            "outcome": "Headaches",
                            "confidence": "Moderate",
                            "text": "Pressure often matches your headache pattern."
                        },
                        "gauge_keys": ["pain", "focus"],
                        "current_context_badge": "Pattern match",
                        "pending_follow_up": {
                            "id": "prompt-1",
                            "episode_id": "ep-1",
                            "symptom_code": "HEADACHE",
                            "symptom_label": "Headache",
                            "question_text": "Still feeling headache?",
                            "detail_focus": "pain",
                            "trigger": "logged",
                            "scheduled_for": "2026-03-23T12:00:00Z",
                            "delivered_at": "2026-03-23T12:05:00Z",
                            "status": "pending",
                            "push_delivery_enabled": true
                        }
                    }
                ],
                "contributing_drivers": [],
                "pattern_context": [],
                "follow_up_settings": {
                    "notifications_enabled": true,
                    "enabled": true,
                    "notification_family_enabled": true,
                    "push_enabled": true,
                    "cadence": "balanced",
                    "states": ["new", "ongoing", "improving", "worse"],
                    "symptom_codes": []
                }
            }
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let envelope = try decoder.decode(Envelope<CurrentSymptomsSnapshot>.self, from: payload)
        let snapshot = try #require(envelope.payload)

        #expect(snapshot.summary.activeCount == 1)
        #expect(snapshot.summary.worseCount == 0)
        #expect(snapshot.items.first?.currentState == .ongoing)
        #expect(snapshot.items.first?.pendingFollowUp?.questionText == "Still feeling headache?")
        #expect(snapshot.items.first?.likelyDrivers.first?.key == "pressure")
        #expect(snapshot.followUpSettings.enabled == true)
        #expect(snapshot.followUpSettings.pushEnabled == true)
    }

    @Test
    func decodesDailyCheckInStatus() throws {
        let payload = """
        {
            "ok": true,
            "data": {
                "prompt": {
                    "id": "daily-1",
                    "day": "2026-03-25",
                    "phase": "next_morning",
                    "question_text": "How did yesterday feel?",
                    "scheduled_for": "2026-03-26T14:00:00Z",
                    "delivered_at": "2026-03-26T14:01:00Z",
                    "active_symptom_labels": ["Headache", "Fatigue"],
                    "recent_symptom_codes": ["HEADACHE", "FATIGUE"],
                    "pain_logged_recently": true,
                    "energy_logged_recently": true,
                    "mood_logged_recently": false,
                    "sleep_logged_recently": true,
                    "suggested_pain_types": ["sinus_pressure", "head_pressure"],
                    "suggested_energy_details": ["drained", "brain_fog"],
                    "suggested_mood_types": ["anxious"],
                    "suggested_sleep_impacts": ["yes_strongly", "not_much"],
                    "push_delivery_enabled": true,
                    "status": "pending"
                },
                "latest_entry": {
                    "day": "2026-03-24",
                    "prompt_id": "daily-0",
                    "compared_to_yesterday": "worse",
                    "energy_level": "low",
                    "usable_energy": "limited",
                    "system_load": "heavy",
                    "pain_level": "noticeable",
                    "pain_type": "head_pressure",
                    "energy_detail": "brain_fog",
                    "mood_level": "slightly_off",
                    "mood_type": "anxious",
                    "sleep_impact": "yes_somewhat",
                    "prediction_match": "partly_right",
                    "note_text": "Rough morning, steadier later.",
                    "completed_at": "2026-03-25T02:00:00Z"
                },
                "calibration_summary": {
                    "window_days": 21,
                    "total_checkins": 5,
                    "mostly_right": 2,
                    "partly_right": 2,
                    "not_really": 1,
                    "match_rate": 0.4,
                    "resolved_count": 3,
                    "improving_count": 4,
                    "worse_count": 1
                },
                "settings": {
                    "enabled": true,
                    "push_enabled": true,
                    "cadence": "balanced",
                    "reminder_time": "20:00"
                }
            }
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let envelope = try decoder.decode(Envelope<DailyCheckInStatus>.self, from: payload)
        let status = try #require(envelope.payload)

        #expect(status.prompt?.phase == "next_morning")
        #expect(status.prompt?.suggestedPainTypes == ["sinus_pressure", "head_pressure"])
        #expect(status.latestEntry?.usableEnergy == "limited")
        #expect(status.calibrationSummary.totalCheckins == 5)
        #expect(status.settings.pushEnabled == true)
    }

    @Test
    func decodesUserExperienceProfileEnvelope() throws {
        let payload = """
        {
            "ok": true,
            "preferences": {
                "mode": "scientific",
                "guide": "cat",
                "tone": "balanced",
                "lunar_sensitivity_declared": true,
                "onboarding_step": "notifications",
                "onboarding_completed": true,
                "onboarding_completed_at": "2026-03-27T20:00:00Z",
                "healthkit_requested_at": "2026-03-27T19:00:00Z",
                "last_backfill_at": "2026-03-27T18:00:00Z"
            }
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let envelope = try decoder.decode(UserExperienceProfileEnvelope.self, from: payload)
        let preferences = try #require(envelope.preferences)

        #expect(envelope.ok == true)
        #expect(preferences.lunarSensitivityDeclared == true)
        #expect(preferences.onboardingStep == .notifications)
        #expect(preferences.onboardingCompleted == true)
        #expect(preferences.onboardingCompletedAt == "2026-03-27T20:00:00Z")
        #expect(preferences.healthkitRequestedAt == "2026-03-27T19:00:00Z")
        #expect(preferences.lastBackfillAt == "2026-03-27T18:00:00Z")
    }

    @Test
    func decodesAllDriversSnapshot() throws {
        let payload = """
        {
            "ok": true,
            "data": {
                "generated_at": "2026-03-26T12:00:00Z",
                "asof": "2026-03-26T11:55:00Z",
                "day": "2026-03-26",
                "summary": {
                    "active_driver_count": 2,
                    "total_count": 3,
                    "strongest_category": "Space",
                    "primary_state": "Strong",
                    "note": "Solar Wind is leading right now.",
                    "has_personal_patterns": true
                },
                "has_personal_patterns": true,
                "filters": [
                    {
                        "key": "all",
                        "label": "All"
                    },
                    {
                        "key": "space",
                        "label": "Space"
                    }
                ],
                "drivers": [
                    {
                        "id": "solar_wind",
                        "key": "solar_wind",
                        "source_key": "sw",
                        "aliases": ["solar_wind", "sw"],
                        "label": "Solar Wind",
                        "category": "space",
                        "category_label": "Space",
                        "role": "leading",
                        "role_label": "Leading now",
                        "state": "strong",
                        "state_label": "Strong",
                        "severity": "high",
                        "reading": "720 km/s",
                        "reading_value": 720,
                        "reading_unit": "km/s",
                        "short_reason": "Solar wind speed is elevated right now.",
                        "personal_reason": "Solar wind often matches fatigue for you.",
                        "current_symptoms": ["Fatigue"],
                        "historical_symptoms": ["Fatigue", "Low Energy"],
                        "pattern_status": "strong",
                        "pattern_status_label": "Strong pattern",
                        "pattern_summary": "Elevated solar wind often matches fatigue for you.",
                        "pattern_evidence_count": 1,
                        "pattern_lag_hours": 12,
                        "pattern_refs": [],
                        "outlook_relevance": "24h",
                        "outlook_summary": "Still worth watching over the next 24 hours.",
                        "updated_at": "2026-03-26T11:55:00Z",
                        "asof": "2026-03-26T11:55:00Z",
                        "what_it_is": "The speed and pressure of charged particles flowing from the Sun.",
                        "active_now_text": "Solar wind speed is running near 720 km/s right now.",
                        "science_note": "Higher solar-wind speed can support more noticeable geomagnetic coupling when conditions line up.",
                        "source_hint": "Current environmental signal",
                        "signal_strength": 0.96,
                        "personal_relevance_score": 1.0,
                        "display_score": 1.0,
                        "is_objectively_active": true
                    }
                ],
                "setup_hints": [
                    {
                        "key": "health_data",
                        "label": "Connect health data",
                        "reason": "Body context gets better when your baseline data is available."
                    }
                ]
            }
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let snapshot = try decoder.decode(AllDriversSnapshot.self, from: payload)

        #expect(snapshot.summary.activeDriverCount == 2)
        #expect(snapshot.drivers.first?.key == "solar_wind")
        #expect(snapshot.drivers.first?.role == .leading)
        #expect(snapshot.drivers.first?.category == .space)
        #expect(snapshot.drivers.first?.matches(focusKey: "sw") == true)
        #expect(snapshot.setupHints.first?.key == "health_data")
    }
}
