import XCTest

// Decode the raw request, never a JSONSerialization/Double round trip.
private struct G038FollowUpRequest: Decodable {
    struct Migraine: Decodable {
        struct Medicine: Decodable {
            let dose_amount: Decimal?
            let reported_relief: String?
        }
        let medicines: [Medicine]
    }
    let migraine: Migraine
}

final class MigraineAppIntegrationUITests: XCTestCase {
    private let episode = "33333333-3333-4333-8333-333333333333"
    override func setUpWithError() throws { continueAfterFailure = false }

    @MainActor private func launch(_ scenario: String = "success", large: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-gaia-verify-normal-app", "-gaia-app-scenario", scenario,
            "-gaia-enable-structured-migraine-follow-up", "-gaia-enable-migraine-calendar", "-gaia-enable-migraine-time-editing"]
        if large { app.launchArguments.append("-gaia-app-large-text") }
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 15), "Must launch the real ContentView tab shell")
        reveal(app.buttons["home-current-symptoms-open"], app)
        capture(app, large ? "G038 accessibility3 Home entry" : "G038 normal Home entry")
        tap(app.buttons["home-current-symptoms-open"], app)
        XCTAssertTrue(app.buttons["symptoms-migraine-calendar-open"].waitForExistence(timeout: 10))
        capture(app, large ? "G038 accessibility3 Symptoms entry" : "G038 normal Symptoms entry")
        do {
            let startup = try receipts(app)
            XCTAssertTrue(startup.allSatisfy { $0["method"] as? String == "GET" }, "No write before isolation receipt acceptance")
            XCTAssertTrue(startup.contains { $0["path"] as? String == "/v1/symptoms/current" })
        } catch { XCTFail("Cannot verify isolated startup: \(error)") }
        return app
    }
    @MainActor private func reveal(_ item: XCUIElement, _ app: XCUIApplication, up: Bool = false) {
        for _ in 0..<24 {
            let top = app.navigationBars.firstMatch.frame.maxY + 4
            let receiptControl = app.buttons["g038-receipt-open"]
            let unobscuredBottom = receiptControl.exists && receiptControl.isHittable ? receiptControl.frame.minY - 12 : app.frame.maxY - 35
            let bottom = app.keyboards.firstMatch.exists ? app.keyboards.firstMatch.frame.minY - 80 : unobscuredBottom
            if item.exists && item.isHittable && item.frame.minY >= top && item.frame.maxY <= bottom { return }
            let towardTop = item.exists && item.frame != .zero ? item.frame.midY < top : up
            let upward = !towardTop
            let low = min(bottom - 20, app.frame.height * 0.65)
            let high = max(top + 20, app.frame.height * 0.25)
            let origin = app.coordinate(withNormalizedOffset: .zero)
            origin.withOffset(CGVector(dx: app.frame.width * 0.90, dy: upward ? low : high))
                .press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(dx: app.frame.width * 0.90, dy: upward ? high : low)))
        }
        XCTAssertTrue(item.exists && item.isHittable, item.debugDescription)
    }
    @MainActor private func tap(_ item: XCUIElement, _ app: XCUIApplication, up: Bool = false) { reveal(item, app, up: up); item.tap() }
    @MainActor private func editor(_ app: XCUIApplication) {
        tap(app.buttons["current-migraine-details-" + episode], app)
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 10))
    }
    @MainActor private func note(_ text: String, _ app: XCUIApplication) {
        replace(text, in: app.textFields["migraine-history-note"], app)
    }
    @MainActor private func replace(_ text: String, in field: XCUIElement, _ app: XCUIApplication) {
        reveal(field, app)
        let old = field.value as? String ?? ""
        field.tap()
        let keyboardIntroduction = app.otherElements["UIContinuousPathIntroductionView"]
        if keyboardIntroduction.exists { keyboardIntroduction.buttons["Continue"].tap() }
        if !old.isEmpty && old != field.placeholderValue {
            field.press(forDuration: 1.0)
            let selectAll = app.menuItems["Select All"].exists ? app.menuItems["Select All"] : app.buttons["Select All"]
            if selectAll.waitForExistence(timeout: 2) { selectAll.tap(); field.typeText(text) }
            else {
                field.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.5)).tap()
                field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count) + text)
            }
        } else { field.typeText(text) }
        XCTAssertEqual(field.value as? String, text)
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot()); attachment.name = name
        attachment.lifetime = .keepAlways; add(attachment)
    }
    @MainActor private func dismissKeyboard(_ app: XCUIApplication) {
        for _ in 0..<3 {
            guard app.keyboards.firstMatch.exists else { return }
            let top = app.navigationBars.firstMatch.frame.maxY + 24
            let keyboardTop = app.keyboards.firstMatch.frame.minY
            let start = max(top, min(app.frame.height * 0.30, keyboardTop - 160))
            let end = max(start + 100, keyboardTop - 40)
            let origin = app.coordinate(withNormalizedOffset: .zero)
            origin.withOffset(CGVector(dx: app.frame.width * 0.90, dy: start))
                .press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(dx: app.frame.width * 0.90, dy: end)))
        }
        XCTAssertFalse(app.keyboards.firstMatch.exists, "Dismiss the keyboard before accessing the bottom toolbar")
    }
    @MainActor private func receipts(_ app: XCUIApplication) throws -> [[String: Any]] {
        dismissKeyboard(app)
        XCTAssertTrue(app.buttons["g038-receipt-open"].isHittable)
        app.buttons["g038-receipt-open"].tap()
        let value = app.staticTexts["g038-request-receipt"]
        XCTAssertTrue(value.waitForExistence(timeout: 5))
        let data = Data(value.label.utf8)
        let attachment = XCTAttachment(data: data, uniformTypeIdentifier: "public.json")
        attachment.name = "G038 synthetic request receipt"; attachment.lifetime = .keepAlways; add(attachment)
        let result = try XCTUnwrap(try JSONSerialization.jsonObject(with: data) as? [[String: Any]])
        XCTAssertTrue(result.allSatisfy { $0["accepted"] as? Bool == true }, "Unexpected transport must fail closed and fail this test")
        app.buttons["Close receipt"].tap()
        return result
    }
    @MainActor private func voiceReveal(_ item: XCUIElement, _ app: XCUIApplication, up: Bool = false, whole: Bool = true) {
        let appFrame = app.frame
        let top = app.navigationBars.firstMatch.frame.maxY + 8
        let receipt = app.buttons["g038-receipt-open"]
        let keyboardVisible = app.keyboards.firstMatch.exists
        let contentBottom = keyboardVisible ? app.keyboards.firstMatch.frame.minY - 80
            : (receipt.exists && receipt.isHittable ? receipt.frame.minY - 12 : appFrame.maxY - 35)
        // iOS 26 keeps search in a floating bottom bar, outside Keyboard.frame.
        let search = app.searchFields.firstMatch
        let bottom = search.exists && search.isHittable ? min(contentBottom, search.frame.minY - 32) : contentBottom
        for _ in 0..<24 {
            let available = max(80, bottom - top)
            let exists = item.exists
            let frame = exists ? item.frame : .zero
            let readable = frame.maxY > top && frame.minY < bottom
                && (frame.height > available || frame.minY >= top && frame.maxY <= bottom)
            let tappable = frame.midY >= top && frame.midY <= bottom
            if exists && item.isHittable && (whole ? readable : tappable) { return }
            let down = frame != .zero ? frame.minY < top : up
            let needed = frame == .zero ? available * 0.65 : (down ? top - frame.minY + 16 : frame.maxY - bottom + 16)
            // The suggestion strip sits above Keyboard.frame; keep drag starts above both.
            let gestureTop = top + 20
            let gestureBottom = bottom - 20
            let distance = min(max(45, gestureBottom - gestureTop), min(available * 0.65, max(45, needed)))
            let origin = app.coordinate(withNormalizedOffset: .zero)
            let fromY = down ? gestureTop : gestureBottom
            origin.withOffset(CGVector(dx: appFrame.width * 0.90, dy: fromY)).press(forDuration: 0.05,
                thenDragTo: origin.withOffset(CGVector(dx: appFrame.width * 0.90, dy: fromY + (down ? distance : -distance))))
        }
        XCTFail("Could not reveal voice-guide journey control: \(item.debugDescription)")
    }
    @MainActor private func voiceTap(_ item: XCUIElement, _ app: XCUIApplication, up: Bool = false) {
        voiceReveal(item, app, up: up, whole: false); item.tap()
    }

    // G039: use the real app navigation with the same fail-closed synthetic transport.
    @MainActor private func launchVoiceGuide(structured: Bool, large: Bool) throws -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-gaia-verify-normal-app", "-gaia-app-scenario", "success"]
        if structured {
            app.launchArguments += ["-gaia-enable-structured-migraine-follow-up", "-gaia-enable-migraine-calendar", "-gaia-enable-migraine-time-editing"]
        }
        if large {
            app.launchArguments += ["-gaia-app-large-text", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXL"]
        }
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 15))
        voiceTap(app.buttons["home-current-symptoms-open"], app)
        XCTAssertTrue(app.buttons["symptoms-voice-commands-open"].waitForExistence(timeout: 10))
        let before = try receipts(app)
        XCTAssertTrue(before.allSatisfy { $0["method"] as? String == "GET" })
        return app
    }

    @MainActor private func readVoiceGuide(_ app: XCUIApplication, structured: Bool, large: Bool, path: String) {
        let title = app.staticTexts["help-article-title-voice-commands"]
        XCTAssertTrue(title.waitForExistence(timeout: 5))
        capture(app, "G039 \(path) \(large ? "accessibility3" : "standard") guide top")
        let start = app.staticTexts["Say to Siri: “Log a migraine in Gaia Eyes” or “Gaia Eyes, log my migraine”."]
        voiceReveal(start, app)
        XCTAssertTrue(start.exists)
        if large {
            XCTAssertGreaterThan(start.frame.height, 140, "Verify actual enlarged paragraph rendering, not just the launch flag")
        }
        capture(app, "G039 \(path) start commands")
        let stop = app.staticTexts["Say to Siri: “Stop my migraine in Gaia Eyes” or “Gaia Eyes, my migraine is over”."]
        voiceReveal(stop, app); XCTAssertTrue(stop.exists)
        capture(app, "G039 \(path) stop commands")
        for section in ["voice-session", "voice-offline", structured ? "voice-review-structured" : "voice-review-basic"] {
            voiceReveal(app.staticTexts["help-section-" + section], app)
            capture(app, "G039 \(path) " + section)
        }
        XCTAssertEqual(app.staticTexts["help-section-voice-review-basic"].exists, !structured)
        XCTAssertEqual(app.staticTexts["help-section-voice-review-structured"].exists, structured)
        XCTAssertEqual(app.staticTexts["help-section-voice-review-times"].exists, structured)
        if structured {
            voiceReveal(app.staticTexts["help-section-voice-review-times"], app)
            capture(app, "G039 \(path) time guidance")
        }
        let last = app.staticTexts.matching(NSPredicate(format: "label == %@", "Review the dictated words and use the app’s Save button. The two Siri actions above are the supported voice shortcuts for migraine logging.")).firstMatch
        voiceReveal(last, app); XCTAssertTrue(last.isHittable)
        capture(app, "G039 \(path) Dictation end")
        voiceReveal(title, app, up: true)
        XCTAssertTrue(app.navigationBars["Voice commands"].buttons.firstMatch.isHittable)
        capture(app, "G039 \(path) returned to guide top")
        app.navigationBars["Voice commands"].buttons.firstMatch.tap()
    }

    @MainActor private func verifySettingsVoiceGuide(large: Bool) throws {
        let app = try launchVoiceGuide(structured: large, large: large)
        app.buttons["Close"].tap()
        XCTAssertTrue(app.buttons["Settings"].waitForExistence(timeout: 5))
        app.buttons["Settings"].tap()
        voiceTap(app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Help Center and reports")).firstMatch, app)
        voiceReveal(app.buttons["settings-voice-commands-open"], app)
        capture(app, "G039 Settings contextual entry")
        app.buttons["settings-voice-commands-open"].tap()
        readVoiceGuide(app, structured: large, large: large, path: "Settings")
        voiceTap(app.buttons["Open Help Center"], app)
        let listEntry = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Voice commands")).firstMatch
        voiceTap(listEntry, app)
        XCTAssertTrue(app.staticTexts["help-article-title-voice-commands"].waitForExistence(timeout: 5))
        capture(app, "G039 Help launch list opens same article")
        app.navigationBars["Voice commands"].buttons.firstMatch.tap()
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 5)); search.tap(); search.typeText("Siri migraine\n")
        let result = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "Voice commands")).firstMatch
        voiceTap(result, app)
        XCTAssertTrue(app.staticTexts["help-article-title-voice-commands"].waitForExistence(timeout: 5))
        capture(app, "G039 Help search opens same article")
        app.navigationBars["Voice commands"].buttons.firstMatch.tap()
        // Search presentation can hide Help Center's navigation bar. Cancel search first.
        if app.buttons["close"].firstMatch.exists { app.buttons["close"].firstMatch.tap() }
        let helpBar = app.navigationBars["Help Center"]
        XCTAssertTrue(helpBar.waitForExistence(timeout: 5))
        helpBar.buttons.firstMatch.tap()
        // Dismiss the Settings sheet via its own bar, not the underlying Home bar.
        let bar = app.navigationBars["Settings"]
        XCTAssertTrue(bar.waitForExistence(timeout: 5))
        // At large text, the first pull can return the long Settings scroll view to its top.
        // Pull again from its own bar once at the top, and verify actual sheet dismissal.
        for _ in 0..<3 {
            if !bar.exists { break }
            bar.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).press(forDuration: 0.1,
                thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.95)))
            if bar.waitForNonExistence(timeout: 1) { break }
        }
        XCTAssertTrue(bar.waitForNonExistence(timeout: 5), "Settings sheet must actually dismiss")
        XCTAssertTrue(app.tabBars.buttons["Home"].waitForExistence(timeout: 5))
        voiceTap(app.buttons["home-current-symptoms-open"], app)
        let after = try receipts(app)
        XCTAssertTrue(after.allSatisfy { $0["method"] as? String == "GET" }, "Reading Settings/Help/search must cause no mutation")
    }

    @MainActor private func verifyContextualVoiceGuide(large: Bool) throws {
        let app = try launchVoiceGuide(structured: true, large: large)
        let episodeEntry = app.buttons["current-migraine-details-" + episode]
        XCTAssertTrue(episodeEntry.exists)
        capture(app, "G039 Symptoms contextual entry")
        voiceTap(app.buttons["symptoms-voice-commands-open"], app)
        readVoiceGuide(app, structured: true, large: large, path: "Symptoms")
        XCTAssertTrue(episodeEntry.exists, "Same synthetic episode remains after Help")
        voiceTap(app.buttons["Log symptom"], app, up: true)
        XCTAssertTrue(app.navigationBars["Log Symptoms"].waitForExistence(timeout: 5))
        voiceTap(app.buttons["Migraine"].firstMatch, app)
        let notes = app.descendants(matching: .any).matching(identifier: "symptom-log-notes").firstMatch
        voiceReveal(notes, app); notes.tap()
        // New disposable simulators may show the first-keyboard tutorial asynchronously.
        if app.buttons["Continue"].waitForExistence(timeout: 2) { app.buttons["Continue"].tap() }
        replace("G039 unsaved guide navigation draft", in: notes, app)
        voiceReveal(app.buttons["log-migraine-voice-commands-open"], app, up: true)
        capture(app, "G039 Log Symptoms contextual entry")
        app.buttons["log-migraine-voice-commands-open"].tap()
        readVoiceGuide(app, structured: true, large: large, path: "Log Symptoms")
        if app.buttons["Continue"].exists { app.buttons["Continue"].tap() }
        XCTAssertEqual(notes.value as? String, "G039 unsaved guide navigation draft")
        XCTAssertTrue(app.navigationBars.buttons["Save"].isEnabled, "Selected migraine remains in the unsaved draft")
        XCTAssertTrue(app.buttons["Save 1 Symptom"].exists, "Exactly one migraine remains selected")
        let draft = try JSONSerialization.data(withJSONObject: [
            "notes": try XCTUnwrap(notes.value as? String), "selectedCount": 1,
            "saveEnabled": app.navigationBars.buttons["Save"].isEnabled
        ], options: [.sortedKeys])
        let draftAttachment = XCTAttachment(data: draft, uniformTypeIdentifier: "public.json")
        draftAttachment.name = "G039 retained unsaved draft receipt"
        draftAttachment.lifetime = .keepAlways; add(draftAttachment)
        capture(app, "G039 returned Log Symptoms with retained draft")
        app.navigationBars.buttons["Close"].tap()
        if !app.buttons["symptoms-voice-commands-open"].exists {
            voiceTap(app.buttons["home-current-symptoms-open"], app)
        }
        let after = try receipts(app)
        XCTAssertTrue(after.allSatisfy { $0["method"] as? String == "GET" }, "Reading Help and retaining a draft must cause no mutation")
    }

    @MainActor func testVoiceGuideSettingsSearchBasic() throws { try verifySettingsVoiceGuide(large: false) }
    @MainActor func testVoiceGuideContextualDraft() throws { try verifyContextualVoiceGuide(large: false) }
    @MainActor func testVoiceGuideSettingsActualLargeText() throws { try verifySettingsVoiceGuide(large: true) }
    @MainActor func testVoiceGuideContextualActualLargeText() throws { try verifyContextualVoiceGuide(large: true) }

    @MainActor private func alertButton(_ identifier: String, _ app: XCUIApplication) throws -> XCUIElement {
        // iOS 26 exposes nested parent/child buttons for the same alert action.
        // Use the actually hittable matching action and still verify its resulting state.
        let matches = app.buttons.matching(identifier: identifier)
        XCTAssertTrue(matches.firstMatch.waitForExistence(timeout: 5))
        return try XCTUnwrap(matches.allElementsBoundByIndex.first { $0.isHittable }, matches.debugDescription)
    }
    @MainActor private func pendingClose(_ app: XCUIApplication) throws {
        let close = app.buttons["migraine-history-close"]
        XCTAssertTrue(close.isEnabled); close.tap()
        XCTAssertTrue(app.staticTexts["Close with an unconfirmed save?"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "does not cancel it")).firstMatch.exists)
        capture(app, "G038 intentional unconfirmed exit")
        let keep = try alertButton("migraine-history-keep-editing", app)
        XCTAssertTrue(keep.isEnabled)
        keep.tap()
        XCTAssertFalse(app.staticTexts["Close with an unconfirmed save?"].exists)
        XCTAssertTrue(close.exists)
    }

    @MainActor func testHomeSymptomsSaveSummaryAndCalendar() throws {
        let app = launch(); editor(app); note("G038 saved note", app)
        tap(app.buttons["migraine-history-save"], app)
        XCTAssertTrue(app.staticTexts["Migraine details saved."].waitForExistence(timeout: 10))
        capture(app, "G038 acknowledged save in normal app")
        let sent = try receipts(app).filter { $0["method"] as? String == "PATCH" }
        XCTAssertEqual(sent.count, 1)
        XCTAssertEqual((sent.first?["body"] as? [String: Any])?["notes"] as? String, "G038 saved note")
        tap(app.buttons["migraine-history-summary"], app, up: true)
        XCTAssertTrue(app.staticTexts["migraine-summary-saved"].waitForExistence(timeout: 10))
        reveal(app.staticTexts["migraine-summary-notes"], app)
        XCTAssertEqual(app.staticTexts["migraine-summary-notes"].label, "G038 saved note")
        capture(app, "G038 saved summary from editor")
        app.buttons["migraine-summary-done"].tap(); app.buttons["migraine-history-close"].tap()
        tap(app.buttons["symptoms-migraine-calendar-open"], app)
        XCTAssertTrue(app.staticTexts["migraine-calendar-count"].waitForExistence(timeout: 10))
        tap(app.buttons["migraine-calendar-day-2026-09-09"], app)
        tap(app.buttons["migraine-calendar-summary-" + episode], app)
        XCTAssertTrue(app.staticTexts["migraine-summary-saved"].waitForExistence(timeout: 10))
        reveal(app.staticTexts["migraine-summary-notes"], app)
        XCTAssertEqual(app.staticTexts["migraine-summary-notes"].label, "G038 saved note")
        capture(app, "G038 calendar summary preserves saved note")
    }

    @MainActor func testUnavailableDetailRetryPreservesTypedNote() throws {
        let app = launch("detail-retry"); editor(app)
        XCTAssertTrue(app.staticTexts["migraine-history-unavailable"].waitForExistence(timeout: 10))
        note("Keep my outage note", app); tap(app.buttons["migraine-history-retry-details"], app)
        let loaded = expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: app.buttons["migraine-history-retry-details"])
        wait(for: [loaded], timeout: 10)
        dismissKeyboard(app)
        // Source and the retained failed-run hierarchy show the loaded medicine form below time fields.
        reveal(app.buttons["migraine-medicine-entry-3"], app)
        XCTAssertTrue(app.buttons["migraine-medicine-entry-3"].isEnabled)
        reveal(app.buttons["migraine-history-save"], app)
        XCTAssertTrue(app.buttons["migraine-history-save"].isEnabled)
        reveal(app.textFields["migraine-history-note"], app, up: true)
        XCTAssertEqual(app.textFields["migraine-history-note"].value as? String, "Keep my outage note")
        capture(app, "G038 detail retry retains local note")
        XCTAssertFalse(try receipts(app).contains { $0["method"] as? String == "PATCH" })
    }

    @MainActor func testPendingFollowUpFromSymptomsSavesExactMedicine() throws {
        let app = launch("followup")
        tap(app.buttons["Still active"], app)
        XCTAssertTrue(app.buttons["migraine-medicine-entry-2"].waitForExistence(timeout: 10))
        tap(app.buttons["migraine-medicine-entry-2"], app)
        replace("2.500000000000000001", in: app.textFields["Dose"], app)
        tap(app.buttons["migraine-medicine-relief"], app); app.buttons["No relief"].tap()
        capture(app, "G038 full-app follow-up medicine edit")
        tap(app.buttons["migraine-save-response"], app)
        XCTAssertTrue(app.buttons["symptoms-migraine-calendar-open"].waitForExistence(timeout: 10))
        let request = try XCTUnwrap(try receipts(app).first { ($0["path"] as? String)?.hasSuffix("/respond") == true })
        let rawBody = try XCTUnwrap(request["body_utf8"] as? String)
        let submitted = try JSONDecoder().decode(G038FollowUpRequest.self, from: Data(rawBody.utf8))
        let medicines = submitted.migraine.medicines
        XCTAssertEqual(medicines.count, 3)
        XCTAssertEqual(medicines[1].dose_amount, Decimal(string: "2.500000000000000001", locale: Locale(identifier: "en_US_POSIX")))
        XCTAssertEqual(medicines[1].reported_relief, "none")
        capture(app, "G038 follow-up acknowledged through real Symptoms")
    }

    @MainActor func testUnconfirmedFollowUpKeepsDraftAndAllowsExit() throws {
        let app = launch("followup-uncertain")
        tap(app.buttons["Still active"], app)
        tap(app.buttons["migraine-medicine-entry-2"], app)
        replace("7.25", in: app.textFields["Dose"], app)
        tap(app.buttons["migraine-save-response"], app)
        XCTAssertTrue(app.buttons["Retry same response"].waitForExistence(timeout: 10))
        app.buttons["migraine-followup-close"].tap()
        let alert = app.staticTexts["Close with an unconfirmed response?"]
        XCTAssertTrue(alert.waitForExistence(timeout: 5))
        let keep = try alertButton("migraine-followup-keep-editing", app)
        XCTAssertTrue(keep.isEnabled)
        XCTAssertTrue(try alertButton("migraine-followup-discard-and-close", app).isEnabled)
        capture(app, "G038 follow-up visible Keep editing and discard")
        keep.tap()
        XCTAssertTrue(app.buttons["Retry same response"].exists)
        reveal(app.textFields["Dose"], app, up: true)
        XCTAssertEqual(app.textFields["Dose"].value as? String, "7.25")
        XCTAssertFalse(app.textFields["Dose"].isEnabled)
        app.buttons["migraine-followup-close"].tap()
        try alertButton("migraine-followup-discard-and-close", app).tap()
        XCTAssertTrue(app.buttons["symptoms-migraine-calendar-open"].waitForExistence(timeout: 5))
        let writes = try receipts(app).filter { $0["method"] as? String != "GET" }
        XCTAssertEqual(writes.count, 1, "Keep editing and deliberate close must send no extra save or cancellation")
        let raw = try XCTUnwrap(writes.first?["body_utf8"] as? String)
        let submitted = try JSONDecoder().decode(G038FollowUpRequest.self, from: Data(raw.utf8))
        XCTAssertEqual(submitted.migraine.medicines.count, 3)
        XCTAssertEqual(submitted.migraine.medicines[1].dose_amount, Decimal(string: "7.25"))
        capture(app, "G038 unconfirmed follow-up deliberately closed")
    }

    @MainActor func testExactDetailCapabilitySignalsAndMissingEpisode() throws {
        for scenario in ["detail-unavailable", "detail-old-route", "detail-missing"] {
            let app = launch(scenario); editor(app)
            let message = app.staticTexts["migraine-history-unavailable"]
            XCTAssertTrue(message.waitForExistence(timeout: 10))
            XCTAssertEqual(message.label.contains("not available yet"), scenario != "detail-missing")
            capture(app, "G038 " + scenario); _ = try receipts(app)
            XCTAssertTrue(app.buttons["migraine-history-close"].isEnabled); app.terminate()
        }
    }

    @MainActor func testCalendarUnavailableViaTimeline() {
        let app = launch("calendar-unavailable")
        tap(app.buttons["symptom-timeline-open"], app)
        tap(app.buttons["migraine-calendar-open"], app)
        let message = app.staticTexts["migraine-calendar-error"]
        XCTAssertTrue(message.waitForExistence(timeout: 10))
        XCTAssertTrue(message.label.contains("not available on this server yet"))
        XCTAssertFalse(app.staticTexts["migraine-calendar-count"].exists)
        capture(app, "G038 timeline to unavailable calendar")
    }

    @MainActor func testUnconfirmedMedicineRetryAndExplicitExit() throws {
        let app = launch("detail-uncertain"); editor(app); note("Unconfirmed local note", app)
        tap(app.buttons["migraine-history-save"], app)
        XCTAssertTrue(app.buttons["Retry same migraine save"].waitForExistence(timeout: 10))
        try pendingClose(app)
        tap(app.buttons["migraine-history-save"], app)
        let completed = expectation(for: NSPredicate(format: "enabled == true"), evaluatedWith: app.buttons["migraine-history-close"])
        wait(for: [completed], timeout: 10)
        let sent = try receipts(app).filter { $0["method"] as? String == "PATCH" }
        XCTAssertEqual(sent.count, 2)
        XCTAssertEqual(sent[0]["body"] as? NSDictionary, sent[1]["body"] as? NSDictionary)
        app.buttons["migraine-history-close"].tap(); try alertButton("migraine-history-discard-and-close", app).tap()
        XCTAssertTrue(app.buttons["symptoms-migraine-calendar-open"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["Migraine details saved."].exists)
    }

    @MainActor func testUnconfirmedTimeRetryUnavailableReloadAndExit() throws {
        let app = launch("time-uncertain"); editor(app)
        let startMode = app.switches["migraine-time-start-mode"]
        reveal(startMode, app)
        XCTAssertTrue(startMode.isEnabled, "Saved time context must be ready before editing")
        XCTAssertEqual(startMode.value as? String, "0")
        // Hit the actual switch, then prove the state changed before searching inserted lazy rows.
        startMode.coordinate(withNormalizedOffset: CGVector(dx: 0.93, dy: 0.5)).tap()
        let enabled = expectation(for: NSPredicate(format: "value == %@", "1"), evaluatedWith: startMode)
        wait(for: [enabled], timeout: 5)
        reveal(app.staticTexts["migraine-time-saved-start"], app, up: true)
        replace("00:15", in: app.textFields["migraine-time-start-clock"], app)
        tap(app.buttons["migraine-time-save"], app)
        XCTAssertTrue(app.buttons["Retry same correction"].waitForExistence(timeout: 10))
        try pendingClose(app); tap(app.buttons["migraine-time-save"], app)
        let unavailable = app.staticTexts["migraine-time-message"]
        let replied = expectation(for: NSPredicate(format: "label CONTAINS %@", "Time editing is unavailable"), evaluatedWith: unavailable)
        wait(for: [replied], timeout: 10)
        tap(app.buttons["migraine-time-reload"], app)
        let reloaded = expectation(for: NSPredicate(format: "label CONTAINS %@", "Time editing is not available yet"), evaluatedWith: unavailable)
        wait(for: [reloaded], timeout: 10)
        let sent = try receipts(app).filter { ($0["path"] as? String)?.hasSuffix("/migraine-times") == true && $0["method"] as? String != "GET" }
        XCTAssertEqual(sent.count, 2)
        XCTAssertEqual(sent[0]["body"] as? NSDictionary, sent[1]["body"] as? NSDictionary)
        try pendingClose(app); app.buttons["migraine-history-close"].tap(); try alertButton("migraine-history-discard-and-close", app).tap()
        XCTAssertTrue(app.buttons["symptoms-migraine-calendar-open"].waitForExistence(timeout: 5))
    }

    @MainActor func testAccountReplacementRejectsDelayedSaveAndAllowsExit() throws {
        let app = launch("delayed-account"); editor(app); note("Old account pending note", app)
        tap(app.buttons["migraine-history-save"], app)
        XCTAssertTrue(app.buttons["Saving migraine details…"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["migraine-history-close"].isEnabled)
        app.buttons["g038-switch-account"].tap()
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "signed-in account changed")).firstMatch.waitForExistence(timeout: 10))
        XCTAssertFalse(app.textFields["migraine-history-note"].exists)
        XCTAssertFalse(app.staticTexts["Migraine details saved."].exists)
        capture(app, "G038 account replacement rejects old response")
        let receipt = try receipts(app)
        XCTAssertFalse(receipt.contains { $0["scope"] as? String == "different-fixture-account" && $0["method"] as? String == "PATCH" })
        app.buttons["migraine-history-close"].tap()
        XCTAssertTrue(app.staticTexts["current-symptoms-account-changed"].waitForExistence(timeout: 5))
    }

    @MainActor func testLargeTextNormalNavigationAndTimeUnavailable() throws {
        let app = launch("time-unavailable", large: true); editor(app)
        let message = app.staticTexts["migraine-time-message"]; reveal(message, app)
        XCTAssertTrue(message.label.contains("Time editing is not available yet"))
        XCTAssertGreaterThan(message.frame.height, 50)
        capture(app, "G038 accessibility3 time unavailable in normal app")
        tap(app.buttons["migraine-medicine-entry-2"], app)
        replace("2.500000000000000001", in: app.textFields["Dose"], app)
        reveal(app.buttons["migraine-medicine-relief"], app)
        capture(app, "G038 accessibility3 medicine editing in normal app")
        // Closing the editor is the normal way to leave this unsaved large-text draft.
        // Read the same no-write receipt after the keyboard leaves with its sheet.
        app.buttons["migraine-history-close"].tap()
        XCTAssertTrue(app.buttons["symptoms-migraine-calendar-open"].waitForExistence(timeout: 5))
        XCTAssertFalse(try receipts(app).contains { $0["method"] as? String == "PATCH" })
        tap(app.buttons["symptoms-migraine-calendar-open"], app)
        tap(app.buttons["migraine-calendar-day-2026-09-09"], app)
        tap(app.buttons["migraine-calendar-summary-" + episode], app)
        XCTAssertTrue(app.staticTexts["migraine-summary-saved"].waitForExistence(timeout: 10))
        capture(app, "G038 accessibility3 saved summary")
        let duration = app.staticTexts["migraine-summary-duration-line-0"]
        reveal(duration, app)
        XCTAssertGreaterThan(duration.frame.height, 30, "The presented summary must actually use accessibility text sizing")
        let dose = app.staticTexts["migraine-summary-medicine-1-line-1"]
        reveal(dose, app)
        XCTAssertEqual(dose.label, "Dose: 2.500000000000000001 mg")
        capture(app, "G038 accessibility3 saved exact medicine")
        reveal(app.staticTexts["migraine-summary-notes"], app)
        XCTAssertEqual(app.staticTexts["migraine-summary-notes"].label, "Keep notes")
        capture(app, "G038 accessibility3 saved episode notes")
    }
}
