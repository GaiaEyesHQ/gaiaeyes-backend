//
//  GaiaExporterTests.swift
//  GaiaExporterTests
//
//  Created by Jennifer O'Brien on 8/24/25.
//

import Foundation
import Testing
@testable import GaiaExporter

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
                        "current_context_badge": "Pattern match"
                    }
                ],
                "contributing_drivers": [],
                "pattern_context": [],
                "follow_up_settings": {
                    "notifications_enabled": true,
                    "enabled": true,
                    "notification_family_enabled": true,
                    "cadence": "balanced",
                    "states": ["new", "ongoing", "improving"],
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
        #expect(snapshot.items.first?.currentState == .ongoing)
        #expect(snapshot.items.first?.likelyDrivers.first?.key == "pressure")
        #expect(snapshot.followUpSettings.enabled == true)
    }
}
