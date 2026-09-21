import XCTest

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
        tap(app.buttons["home-current-symptoms-open"], app)
        XCTAssertTrue(app.buttons["symptoms-migraine-calendar-open"].waitForExistence(timeout: 10))
        return app
    }
    @MainActor private func reveal(_ item: XCUIElement, _ app: XCUIApplication) {
        for _ in 0..<24 {
            let top = app.navigationBars.firstMatch.frame.maxY + 4
            let bottom = app.keyboards.firstMatch.exists ? app.keyboards.firstMatch.frame.minY - 20 : app.frame.maxY - 95
            if item.exists && item.isHittable && item.frame.minY >= top && item.frame.maxY <= bottom { return }
            let upward = !item.exists || item.frame.minY > top
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.96, dy: upward ? 0.65 : 0.26))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.96, dy: upward ? 0.25 : 0.65)))
        }
        XCTAssertTrue(item.exists && item.isHittable, item.debugDescription)
    }
    @MainActor private func tap(_ item: XCUIElement, _ app: XCUIApplication) { reveal(item, app); item.tap() }
    @MainActor private func editor(_ app: XCUIApplication) {
        tap(app.buttons["current-migraine-details-" + episode], app)
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 10))
    }
    @MainActor private func note(_ text: String, _ app: XCUIApplication) {
        let field = app.textFields["migraine-history-note"]; reveal(field, app); field.tap()
        let old = field.value as? String ?? ""
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count) + text)
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot()); attachment.name = name
        attachment.lifetime = .keepAlways; add(attachment)
    }
    @MainActor private func receipts(_ app: XCUIApplication) throws -> [[String: Any]] {
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
    @MainActor private func pendingClose(_ app: XCUIApplication) {
        let close = app.buttons["migraine-history-close"]
        XCTAssertTrue(close.isEnabled); close.tap()
        XCTAssertTrue(app.staticTexts["Close with an unconfirmed save?"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "does not cancel it")).firstMatch.exists)
        capture(app, "G038 intentional unconfirmed exit")
        app.buttons["Keep editing"].tap()
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
        tap(app.buttons["migraine-history-summary"], app)
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
        XCTAssertTrue(app.buttons["migraine-history-save"].waitForExistence(timeout: 10))
        reveal(app.textFields["migraine-history-note"], app)
        XCTAssertEqual(app.textFields["migraine-history-note"].value as? String, "Keep my outage note")
        capture(app, "G038 detail retry retains local note")
        XCTAssertFalse(try receipts(app).contains { $0["method"] as? String == "PATCH" })
    }

    @MainActor func testPendingFollowUpFromSymptomsSavesExactMedicine() throws {
        let app = launch("followup")
        tap(app.buttons["Still active"], app)
        XCTAssertTrue(app.buttons["migraine-medicine-entry-2"].waitForExistence(timeout: 10))
        tap(app.buttons["migraine-medicine-entry-2"], app)
        let dose = app.textFields["Dose"]; reveal(dose, app); dose.tap()
        dose.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: (dose.value as? String ?? "").count) + "2.500000000000000001")
        tap(app.buttons["migraine-medicine-relief"], app); app.buttons["No relief"].tap()
        capture(app, "G038 full-app follow-up medicine edit")
        tap(app.buttons["migraine-save-response"], app)
        XCTAssertTrue(app.buttons["symptoms-migraine-calendar-open"].waitForExistence(timeout: 10))
        let request = try XCTUnwrap(try receipts(app).first { ($0["path"] as? String)?.hasSuffix("/respond") == true })
        let edit = try XCTUnwrap((request["body"] as? [String: Any])?["migraine"] as? [String: Any])
        let medicines = try XCTUnwrap(edit["medicines"] as? [[String: Any]])
        XCTAssertEqual(medicines.count, 3)
        XCTAssertEqual(medicines[1]["dose_amount"] as? String, "2.500000000000000001")
        XCTAssertEqual(medicines[1]["reported_relief"] as? String, "none")
        capture(app, "G038 follow-up acknowledged through real Symptoms")
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
        pendingClose(app)
        tap(app.buttons["migraine-history-save"], app)
        let completed = expectation(for: NSPredicate(format: "enabled == true"), evaluatedWith: app.buttons["migraine-history-close"])
        wait(for: [completed], timeout: 10)
        let sent = try receipts(app).filter { $0["method"] as? String == "PATCH" }
        XCTAssertEqual(sent.count, 2)
        XCTAssertEqual(sent[0]["body"] as? NSDictionary, sent[1]["body"] as? NSDictionary)
        app.buttons["migraine-history-close"].tap(); app.buttons["Discard local draft and close"].tap()
        XCTAssertTrue(app.buttons["symptoms-migraine-calendar-open"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.staticTexts["Migraine details saved."].exists)
    }

    @MainActor func testUnconfirmedTimeRetryUnavailableReloadAndExit() throws {
        let app = launch("time-uncertain"); editor(app)
        tap(app.switches["migraine-time-start-mode"], app)
        let field = app.textFields["migraine-time-start-clock"]; reveal(field, app); field.tap()
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: (field.value as? String ?? "").count) + "00:15")
        tap(app.buttons["migraine-time-save"], app)
        XCTAssertTrue(app.buttons["Retry same correction"].waitForExistence(timeout: 10))
        pendingClose(app); tap(app.buttons["migraine-time-save"], app)
        let unavailable = app.staticTexts["migraine-time-message"]
        let replied = expectation(for: NSPredicate(format: "label CONTAINS %@", "Time editing is unavailable"), evaluatedWith: unavailable)
        wait(for: [replied], timeout: 10)
        tap(app.buttons["migraine-time-reload"], app)
        let reloaded = expectation(for: NSPredicate(format: "label CONTAINS %@", "Time editing is not available yet"), evaluatedWith: unavailable)
        wait(for: [reloaded], timeout: 10)
        let sent = try receipts(app).filter { ($0["path"] as? String)?.hasSuffix("/migraine-times") == true && $0["method"] as? String != "GET" }
        XCTAssertEqual(sent.count, 2)
        XCTAssertEqual(sent[0]["body"] as? NSDictionary, sent[1]["body"] as? NSDictionary)
        pendingClose(app); app.buttons["migraine-history-close"].tap(); app.buttons["Discard local draft and close"].tap()
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
        _ = try receipts(app)
        app.buttons["migraine-history-close"].tap()
        tap(app.buttons["symptoms-migraine-calendar-open"], app)
        tap(app.buttons["migraine-calendar-day-2026-09-09"], app)
        tap(app.buttons["migraine-calendar-summary-" + episode], app)
        XCTAssertTrue(app.staticTexts["migraine-summary-saved"].waitForExistence(timeout: 10))
        capture(app, "G038 accessibility3 saved summary")
    }
}
