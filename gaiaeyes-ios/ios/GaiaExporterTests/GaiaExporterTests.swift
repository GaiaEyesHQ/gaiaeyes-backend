//
//  GaiaExporterTests.swift
//  GaiaExporterTests
//
//  Created by Jennifer O'Brien on 8/24/25.
//

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
}
