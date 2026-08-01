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
    func possibleSymptomsTranslateShortSleepIntoNoticeableOutcomes() {
        #expect(HomePossibleSymptomLabels.labels(forOutcomeKey: "short_sleep_day") == ["Low energy"])
        #expect(HomePossibleSymptomLabels.labels(forOutcomeKey: "hrv_dip_day") == ["Low energy"])
        #expect(!HomePossibleSymptomLabels.labels(forOutcomeKey: "short_sleep_day").contains("Sleep debt"))
    }

    @Test
    func possibleSymptomsKeepAndPrioritizeActiveMatches() {
        let ranked = HomePossibleSymptomLabels.ranked(
            candidates: ["Tired", "Low energy", "Poor sleep", "Restless sleep", "Brain fog", "restless sleep"],
            activeLabels: [" tired ", "Restless Sleep"]
        )

        #expect(ranked == [
            HomePossibleSymptomMatch(label: "Low energy", isMatched: true),
            HomePossibleSymptomMatch(label: "Restless sleep", isMatched: true),
            HomePossibleSymptomMatch(label: "Brain fog", isMatched: false),
        ])
    }

    @Test
    func poorSleepOutcomeUsesOneSpecificSymptomLabel() {
        #expect(HomePossibleSymptomLabels.labels(forOutcomeKey: "poor_sleep_day") == ["Restless sleep"])
    }

    @Test
    func outlookUsesSolarFlareLabelForCachedBackendCopy() {
        #expect(OutlookDisplayLabels.driverLabel(key: "flare", fallback: "Flare watch") == "Solar Flare Watch")
        #expect(OutlookDisplayLabels.driverLabel(key: "flare_watch", fallback: "Flare watch") == "Solar Flare Watch")
        #expect(OutlookDisplayLabels.driverLabel(key: "forecast_flag", fallback: "Flare watch") == "Solar Flare Watch")
    }

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
    func decodesExposureSaveEnvelopeWithAPIKeyStrategy() throws {
        let payload = """
        {
            "ok": true,
            "data": {
                "id": "exposure-123",
                "exposure_key": "rapid_temperature_change",
                "intensity": 1,
                "event_ts_utc": "2026-07-14T22:56:00Z",
                "source": "manual",
                "note_text": null
            }
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let envelope = try decoder.decode(Envelope<ExposureEventOut>.self, from: payload)
        let exposure = try #require(envelope.payload)

        #expect(exposure.exposureKey == "rapid_temperature_change")
        #expect(exposure.intensity == 1)
        #expect(exposure.eventTsUtc == "2026-07-14T22:56:00Z")
        #expect(exposure.source == "manual")
    }

    @Test
    func normalizesQueuedEventCodes() {
        let event = SymptomQueuedEvent(symptomCode: "nerve pain")
        #expect(event.symptomCode == "NERVE_PAIN")
        #expect(event.severity == 5)
    }

    @Test
    func decodesSymptomPostEnvelopeData() throws {
        let payload = """
        {
            "ok": true,
            "data": {
                "id": "evt-123",
                "ts_utc": "2026-04-28T18:30:00Z"
            },
            "error": null
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let response = try decoder.decode(SymptomPostResponse.self, from: payload)

        #expect(response.ok == true)
        #expect(response.id == "evt-123")
        #expect(response.tsUtc == "2026-04-28T18:30:00Z")
        #expect(response.error == nil)
    }

    @Test
    func decodesSymptomPostEnvelopeError() throws {
        let payload = """
        {
            "ok": false,
            "data": null,
            "error": "Failed to record symptom event"
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let response = try decoder.decode(SymptomPostResponse.self, from: payload)

        #expect(response.ok == false)
        #expect(response.id == nil)
        #expect(response.error == "Failed to record symptom event")
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

        let cachedData = try JSONEncoder().encode(snapshot)
        let cachedSnapshot = try JSONDecoder().decode(CurrentSymptomsSnapshot.self, from: cachedData)
        #expect(cachedSnapshot == snapshot)
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

struct HandsFreeSymptomLoggerTests {
    private enum TestError: Error {
        case rejected
    }

    @Test
    func migraineRequestUsesCanonicalPayloadDefaults() {
        let date = Date(timeIntervalSince1970: 1_722_000_000)
        let event = HandsFreeSymptomLogRequest.migraine.event(at: date)

        #expect(event.symptomCode == "MIGRAINE")
        #expect(event.severity == 5)
        #expect(event.tsUtc == date)
        #expect(event.freeText == nil)
        #expect(event.tags == nil)
    }

    @Test
    func authenticatedIntentSubmitsThroughCanonicalWriter() async {
        let suiteName = "HandsFreeSymptomLoggerTests.submit.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let capture = SymptomEventCapture()
        let logger = HandsFreeSymptomLogger(
            defaults: defaults,
            tokenProvider: { "valid-token" },
            submitter: { event, token in
                await capture.record(event: event, token: token)
            },
            enqueuer: { _ in
                Issue.record("A successful request must not be queued")
            }
        )

        let result = await logger.log(.migraine)
        let recorded = await capture.value

        #expect(result == .submitted)
        #expect(recorded?.event.symptomCode == "MIGRAINE")
        #expect(recorded?.event.severity == 5)
        #expect(recorded?.token == "valid-token")
    }

    @Test
    func signedOutIntentDoesNotSubmitOrQueue() async {
        let suiteName = "HandsFreeSymptomLoggerTests.auth.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let logger = HandsFreeSymptomLogger(
            defaults: defaults,
            tokenProvider: { nil },
            submitter: { _, _ in
                Issue.record("A signed-out request must not submit")
            },
            enqueuer: { _ in
                Issue.record("A signed-out request must not queue")
            }
        )

        #expect(await logger.log(.migraine) == .signedOut)
    }

    @Test
    func offlineIntentQueuesAndReportsSaved() async {
        let suiteName = "HandsFreeSymptomLoggerTests.offline.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let capture = QueuedSymptomCapture()
        let logger = HandsFreeSymptomLogger(
            defaults: defaults,
            tokenProvider: { "valid-token" },
            submitter: { _, _ in throw URLError(.notConnectedToInternet) },
            enqueuer: { event in await capture.record(event) }
        )

        let result = await logger.log(.migraine)

        #expect(result == .queued)
        #expect(await capture.value?.symptomCode == "MIGRAINE")
    }

    @Test
    func rejectedIntentDoesNotQueueOrClaimSuccess() async {
        let suiteName = "HandsFreeSymptomLoggerTests.rejected.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let logger = HandsFreeSymptomLogger(
            defaults: defaults,
            tokenProvider: { "valid-token" },
            submitter: { _, _ in throw TestError.rejected },
            enqueuer: { _ in
                Issue.record("A rejected request must not be queued as an offline write")
            }
        )

        #expect(await logger.log(.migraine) == .failed)
    }

    @Test
    func retryWithinDuplicateWindowDoesNotSubmitTwice() async {
        let suiteName = "HandsFreeSymptomLoggerTests.duplicate.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let capture = SubmissionCount()
        let date = Date(timeIntervalSince1970: 1_722_000_000)
        let logger = HandsFreeSymptomLogger(
            duplicateWindow: 30,
            defaults: defaults,
            now: { date },
            tokenProvider: { "valid-token" },
            submitter: { _, _ in await capture.increment() },
            enqueuer: { _ in }
        )

        let first = await logger.log(.migraine)
        let retry = await logger.log(.migraine)

        #expect(first == .submitted)
        #expect(retry == .duplicate)
        #expect(await capture.value == 1)
    }
}

struct HandsFreeMigraineResolverTests {
    private enum TestError: Error {
        case unavailable
    }

    @Test
    func resolvesMostRecentlyLoggedActiveMigraine() async {
        let suiteName = "HandsFreeMigraineResolverTests.resolve.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let capture = MigraineResolutionCapture()
        let resolutionDate = Date(timeIntervalSince1970: 1_722_000_000)
        let snapshot = currentSymptomsSnapshot(items: [
            currentSymptom(id: "older", code: "MIGRAINE", loggedAt: "2026-07-31T10:00:00Z"),
            currentSymptom(id: "headache", code: "HEADACHE", loggedAt: "2026-07-31T12:00:00Z"),
            currentSymptom(id: "newer", code: "MIGRAINE", loggedAt: "2026-07-31T11:00:00Z"),
        ])
        let resolver = HandsFreeMigraineResolver(
            defaults: defaults,
            now: { resolutionDate },
            tokenProvider: { "valid-token" },
            snapshotFetcher: { _ in snapshot },
            episodeResolver: { episodeId, token, timestamp in
                await capture.record(episodeId: episodeId, token: token, timestamp: timestamp)
            }
        )

        let result = await resolver.resolveLatestMigraine()
        let recorded = await capture.value

        #expect(result == .resolved)
        #expect(recorded?.episodeId == "newer")
        #expect(recorded?.token == "valid-token")
        #expect(recorded?.timestamp == resolutionDate)
    }

    @Test
    func reportsNoActiveMigraineWithoutUpdatingAnotherSymptom() async {
        let suiteName = "HandsFreeMigraineResolverTests.missing.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let resolver = HandsFreeMigraineResolver(
            defaults: defaults,
            tokenProvider: { "valid-token" },
            snapshotFetcher: { _ in
                currentSymptomsSnapshot(items: [
                    currentSymptom(id: "headache", code: "HEADACHE", loggedAt: "2026-07-31T12:00:00Z")
                ])
            },
            episodeResolver: { _, _, _ in
                Issue.record("A non-migraine symptom must not be resolved")
            }
        )

        #expect(await resolver.resolveLatestMigraine() == .notFound)
    }

    @Test
    func signedOutResolutionDoesNotFetchOrUpdate() async {
        let suiteName = "HandsFreeMigraineResolverTests.auth.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let resolver = HandsFreeMigraineResolver(
            defaults: defaults,
            tokenProvider: { nil },
            snapshotFetcher: { _ in
                Issue.record("A signed-out request must not fetch symptoms")
                return currentSymptomsSnapshot(items: [])
            },
            episodeResolver: { _, _, _ in
                Issue.record("A signed-out request must not resolve a migraine")
            }
        )

        #expect(await resolver.resolveLatestMigraine() == .signedOut)
    }

    @Test
    func failedResolutionDoesNotClaimSuccess() async {
        let suiteName = "HandsFreeMigraineResolverTests.failure.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let resolver = HandsFreeMigraineResolver(
            defaults: defaults,
            tokenProvider: { "valid-token" },
            snapshotFetcher: { _ in
                currentSymptomsSnapshot(items: [
                    currentSymptom(id: "migraine", code: "MIGRAINE", loggedAt: "2026-07-31T12:00:00Z")
                ])
            },
            episodeResolver: { _, _, _ in throw TestError.unavailable }
        )

        #expect(await resolver.resolveLatestMigraine() == .failed)
    }

    @Test
    func retryWithinDuplicateWindowDoesNotResolveTwice() async {
        let suiteName = "HandsFreeMigraineResolverTests.duplicate.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let capture = SubmissionCount()
        let date = Date(timeIntervalSince1970: 1_722_000_000)
        let resolver = HandsFreeMigraineResolver(
            duplicateWindow: 30,
            defaults: defaults,
            now: { date },
            tokenProvider: { "valid-token" },
            snapshotFetcher: { _ in
                currentSymptomsSnapshot(items: [
                    currentSymptom(id: "migraine", code: "MIGRAINE", loggedAt: "2026-07-31T12:00:00Z")
                ])
            },
            episodeResolver: { _, _, _ in await capture.increment() }
        )

        let first = await resolver.resolveLatestMigraine()
        let retry = await resolver.resolveLatestMigraine()

        #expect(first == .resolved)
        #expect(retry == .duplicate)
        #expect(await capture.value == 1)
    }
}

private func currentSymptomsSnapshot(items: [CurrentSymptomItem]) -> CurrentSymptomsSnapshot {
    CurrentSymptomsSnapshot(
        generatedAt: "2026-07-31T12:00:00Z",
        windowHours: 48,
        summary: CurrentSymptomsSummary(
            activeCount: items.count,
            newCount: items.count,
            ongoingCount: 0,
            improvingCount: 0,
            worseCount: 0,
            lastUpdatedAt: "2026-07-31T12:00:00Z",
            followUpAvailable: false
        ),
        items: items,
        contributingDrivers: [],
        patternContext: [],
        followUpSettings: CurrentSymptomsFollowUpSettings(
            notificationsEnabled: false,
            enabled: false,
            notificationFamilyEnabled: false,
            pushEnabled: false,
            cadence: "balanced",
            states: [],
            symptomCodes: []
        ),
        voiceSemantic: nil
    )
}

private func currentSymptom(id: String, code: String, loggedAt: String) -> CurrentSymptomItem {
    CurrentSymptomItem(
        id: id,
        symptomCode: code,
        label: code == "MIGRAINE" ? "Migraine" : "Headache",
        severity: 5,
        originalSeverity: 5,
        loggedAt: loggedAt,
        lastInteractionAt: loggedAt,
        currentState: .new,
        notePreview: nil,
        noteCount: 0,
        likelyDrivers: [],
        patternHint: nil,
        gaugeKeys: [],
        currentContextBadge: nil,
        pendingFollowUp: nil
    )
}

private actor SymptomEventCapture {
    private(set) var value: (event: SymptomQueuedEvent, token: String)?

    func record(event: SymptomQueuedEvent, token: String) {
        value = (event, token)
    }
}

private actor MigraineResolutionCapture {
    private(set) var value: (episodeId: String, token: String, timestamp: Date)?

    func record(episodeId: String, token: String, timestamp: Date) {
        value = (episodeId, token, timestamp)
    }
}

private actor QueuedSymptomCapture {
    private(set) var value: SymptomQueuedEvent?

    func record(_ event: SymptomQueuedEvent) {
        value = event
    }
}

private actor SubmissionCount {
    private(set) var value = 0

    func increment() {
        value += 1
    }
}

struct SignalBarSnapshotTests {

    @Test
    func decodesLegacySnapshotWithoutSpaceBlock() throws {
        let payload = """
        {
            "updated_at": "2026-07-10T16:42:00Z",
            "items": []
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let snapshot = try decoder.decode(SignalBarSnapshot.self, from: payload)

        #expect(snapshot.space == nil)
        #expect(snapshot.items.isEmpty)
    }

    @Test
    func decodesAtomicCurrentSpaceSnapshot() throws {
        let payload = """
        {
            "updated_at": "2026-07-10T16:42:00Z",
            "space": {
                "kp_now": 1.0,
                "kp_max_24h": 3.7,
                "bz_now": null,
                "sw_speed_now_kms": 602.4,
                "sw_density_now_cm3": 7.3,
                "updated_at": "2026-07-10T16:42:00Z"
            },
            "items": [
                {
                    "key": "solar_wind",
                    "label": "SW",
                    "value": "602 km/s",
                    "state": "elevated",
                    "driver_key": "solar_wind",
                    "detail_target": "driver",
                    "updated_at": "2026-07-10T16:42:00Z"
                }
            ]
        }
        """.data(using: .utf8)!

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let snapshot = try decoder.decode(SignalBarSnapshot.self, from: payload)

        #expect(snapshot.space?.kpNow == 1.0)
        #expect(snapshot.space?.kpMax24H == 3.7)
        #expect(snapshot.space?.bzNow == nil)
        #expect(snapshot.space?.swSpeedNowKms == 602.4)
        #expect(snapshot.space?.swDensityNowCm3 == 7.3)
        #expect(snapshot.items.first?.value == "602 km/s")
    }
}

struct ShareEngineTests {

    @Test
    func outlookScientificCaptionUsesLabeledFacts() {
        let captions = ShareCaptionEngine.outlook(
            mode: .scientific,
            category: .air,
            hook: "Humidity is doing more than usual",
            windowTitle: "Next 24 Hours",
            primaryDriver: "Humidity",
            insight: "Next 24 Hours points to Humidity first.",
            bullets: ["Energy", "Pain"],
            supportingDrivers: ["Geomagnetic Outlook"],
            affectedDomains: ["Energy", "Pain"],
            actionLine: "Keep hydration steady and pace a little more evenly.",
            primaryState: "High",
            primaryValue: "93%"
        )

        #expect(captions.scientific.contains("• Window: Next 24 Hours."))
        #expect(captions.scientific.contains("• Leading:"))
        #expect(captions.scientific.contains("• Watch for: Energy, Pain."))
        #expect(captions.scientific.contains("Track the next shifts in Gaia Eyes."))
    }

    @Test
    func airSignalBalancedCaptionUsesLocalCta() {
        let captions = ShareCaptionEngine.signalSnapshot(
            mode: .scientific,
            tone: .balanced,
            category: .air,
            hook: "The air is more reactive right now",
            title: "Humidity",
            insight: "Humidity is high right now.",
            signText: "Sinus watch\nHigh",
            bullets: ["Higher irritant load can line up with sinus, headache, or fatigue days"],
            value: "93%",
            state: "High"
        )

        #expect(captions.balanced.contains("Track the bigger picture in Gaia Eyes."))
        #expect(captions.scientific.contains("• Signal:"))
        #expect(captions.scientific.contains("Track local air shifts in Gaia Eyes."))
    }
}

struct FeaturesTodayRoundTripTests {

    @Test
    func preservesBodyMetricsThroughCacheStyleJSONRoundTrip() throws {
        let payload = """
        {
            "ok": true,
            "data": {
                "day": "2026-04-21",
                "updated_at": "2026-04-22T02:27:12.612489+00:00",
                "steps_total": 2728,
                "hr_min": 52.0233050847458,
                "hr_max": 92.5148305084746,
                "spo2_avg": 97.4646464646465,
                "respiratory_rate_avg": 13.4625719769674,
                "respiratory_rate_sleep_avg": 13.3347368421053,
                "respiratory_rate_baseline_delta": -0.336,
                "resting_hr_avg": 52.0,
                "resting_hr_baseline_delta": -5.929,
                "bedtime_consistency_score": 46.4,
                "waketime_consistency_score": 63.9,
                "sleep_debt_proxy": 0.0,
                "sleep_vs_14d_baseline_delta": 145.2,
                "sleep_total_minutes": 524,
                "rem_m": 97,
                "core_m": 390,
                "deep_m": 38,
                "awake_m": 4,
                "inbed_m": 200,
                "sleep_efficiency": 0.7200118968633462,
                "cycle_tracking_enabled": true,
                "menstrual_active": false,
                "cycle_day": 7,
                "cycle_updated_at": "2026-04-16T17:00:00+00:00"
            }
        }
        """.data(using: .utf8)!

        let apiDecoder = JSONDecoder()
        apiDecoder.keyDecodingStrategy = .convertFromSnakeCase
        let envelope = try apiDecoder.decode(Envelope<FeaturesToday>.self, from: payload)
        let features = try #require(envelope.payload)

        let cachedData = try JSONEncoder().encode(features)

        let cacheDecoder = JSONDecoder()
        cacheDecoder.keyDecodingStrategy = .convertFromSnakeCase
        let roundTripped = try cacheDecoder.decode(FeaturesToday.self, from: cachedData)

        #expect(roundTripped.stepsTotal?.value == 2728)
        #expect(roundTripped.sleepTotalMinutes?.value == 524)
        #expect(roundTripped.spo2Avg?.value == 97.4646464646465)
        #expect(roundTripped.respiratoryRateAvg?.value == 13.4625719769674)
        #expect(roundTripped.restingHrAvg?.value == 52.0)
        #expect(roundTripped.remM?.value == 97)
        #expect(roundTripped.deepM?.value == 38)
    }
}
