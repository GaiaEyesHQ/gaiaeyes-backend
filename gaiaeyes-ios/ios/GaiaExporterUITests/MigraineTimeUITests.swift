import XCTest

final class MigraineTimeUITests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }
    @MainActor private func launch(_ scenario: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-gaia-preview-migraine-follow-up-fixture", "-gaia-enable-migraine-calendar",
            "-gaia-enable-structured-migraine-follow-up", "-gaia-enable-migraine-time-editing", "-gaia-migraine-scenario", scenario]
        app.launch(); return app
    }
    @MainActor private func reveal(_ element: XCUIElement, _ app: XCUIApplication, up: Bool = false) {
        for attempt in 0..<24 {
            let navigation = app.navigationBars["Edit symptom"].exists ? app.navigationBars["Edit symptom"] : app.navigationBars.firstMatch
            let top = navigation.exists ? navigation.frame.maxY + 4 : 120
            let bottom = app.keyboards.firstMatch.exists ? app.keyboards.firstMatch.frame.minY - 45 : app.frame.maxY - 35
            let frame = element.exists ? element.frame : .zero
            // XCTest sometimes calls controls below the keyboard or partly
            // behind the navigation bar hittable. Require visible bounds too.
            if element.exists && element.isHittable && frame.minY >= top && frame.maxY <= bottom { return }
            let towardTop = element.exists && frame != .zero
                ? frame.midY < top : (attempt < 8 ? up : !up)
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: towardTop ? 0.25 : 0.46))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: towardTop ? 0.62 : 0.18)))
        }
        XCTAssertTrue(element.isHittable, element.debugDescription)
    }
    @MainActor private func replace(_ element: XCUIElement, _ value: String, _ app: XCUIApplication, up: Bool = false) {
        reveal(element, app, up: up)
        let old = element.value as? String ?? ""
        // Keep already-correct stored time/zone values. The changed synthetic
        // dates are short enough for a normal tap to put the caret at the end.
        if old == value { return }
        element.tap()
        element.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count) + value)
        XCTAssertEqual(element.value as? String, value)
    }
    @MainActor private func screenshot(_ app: XCUIApplication, _ name: String) {
        let item = XCTAttachment(screenshot: app.screenshot()); item.name = name; item.lifetime = .keepAlways; add(item)
    }
    @MainActor private func start(_ app: XCUIApplication, date: String = "2026-08-31") {
        let toggle = app.switches["migraine-time-start-mode"]; reveal(toggle, app)
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        screenshot(app, "G013 start toggle after tap")
        XCTAssertEqual(toggle.value as? String, "1", toggle.debugDescription)
        replace(app.textFields["migraine-time-start-date"], date, app)
    }
    @MainActor private func save(_ app: XCUIApplication) {
        let button = app.buttons["migraine-time-save"]; reveal(button, app); XCTAssertTrue(button.isEnabled); button.tap()
    }
    @MainActor private func message(_ app: XCUIApplication) -> XCUIElement {
        let status = app.staticTexts["migraine-time-message"]; reveal(status, app); return status
    }

    @MainActor func testCalendarCorrectionCrossesMonthAndReloadsSavedTimes() {
        let app = launch("calendar-time-success")
        XCTAssertTrue(app.staticTexts["migraine-calendar-count"].waitForExistence(timeout: 10))
        let episode = app.buttons["migraine-calendar-episode-33333333-3333-4333-8333-333333333333"]
        reveal(episode, app); episode.tap()
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 8))
        start(app)
        replace(app.textFields["migraine-time-start-clock"], "23:30:00", app)
        let end = app.buttons["migraine-time-end-mode"]; reveal(end, app); end.tap(); app.buttons["Set end"].tap()
        replace(app.textFields["migraine-time-end-date"], "2026-09-01", app)
        replace(app.textFields["migraine-time-end-clock"], "02:30:00", app)
        replace(app.textFields["migraine-time-end-zone"], "America/Chicago", app)
        screenshot(app, "G013 small phone end correction with explicit timezone")
        save(app); XCTAssertEqual(message(app).label, "Migraine times saved.")
        app.buttons["migraine-calendar-editor-done"].tap()
        XCTAssertTrue(app.staticTexts["No migraine episodes recorded for this day."].waitForExistence(timeout: 8))
        let first = app.buttons["migraine-calendar-day-2026-09-01"]; reveal(first, app, up: true); first.tap()
        XCTAssertTrue(app.staticTexts["1 migraine episode"].waitForExistence(timeout: 8))
        app.buttons["migraine-calendar-previous"].tap()
        app.buttons["migraine-calendar-day-2026-08-31"].tap()
        XCTAssertTrue(app.staticTexts["1 migraine episode"].waitForExistence(timeout: 8))
        screenshot(app, "G013 corrected episode on August 31 calendar")
        reveal(episode, app); episode.tap()
        let saved = app.staticTexts["migraine-time-saved-start"]; reveal(saved, app)
        XCTAssertTrue(saved.label.contains("2026-08-31 at 23:30:00"))
        XCTAssertTrue(app.staticTexts["migraine-time-saved-end"].label.contains("2026-09-01 at 02:30:00"))
    }

    @MainActor func testValidationAndConflictKeepIntentForExplicitRecovery() {
        let app = launch("time-history-conflict")
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 8))
        start(app, date: "2026-02-30"); save(app)
        XCTAssertTrue(message(app).label.contains("Enter a date"))
        replace(app.textFields["migraine-time-start-date"], "2026-08-31", app, up: true)
        save(app); XCTAssertTrue(message(app).label.contains("episode changed"))
        XCTAssertFalse(app.buttons["migraine-time-save"].isEnabled)
        screenshot(app, "G013 conflict keeps time draft for explicit reload")
        app.buttons["migraine-time-reload"].tap()
        XCTAssertTrue(message(app).label.contains("intended changes are still here"))
        let field = app.textFields["migraine-time-start-date"]; reveal(field, app, up: true)
        XCTAssertEqual(field.value as? String, "2026-08-31")
        save(app); XCTAssertEqual(message(app).label, "Migraine times saved.")
    }

    @MainActor func testLostResponseRetriesSameCorrectionAndPreservesNonTimeDraft() {
        let app = launch("time-history-lost")
        let note = app.textFields["migraine-history-note"]
        XCTAssertTrue(note.waitForExistence(timeout: 8)); note.tap(); note.typeText(" unsaved here")
        start(app); save(app)
        XCTAssertTrue(message(app).label.contains("could not be confirmed"))
        XCTAssertEqual(app.buttons["migraine-time-save"].label, "Retry same correction")
        screenshot(app, "G013 response loss retains retry and draft")
        save(app); XCTAssertEqual(message(app).label, "Migraine times saved.")
        reveal(note, app, up: true); XCTAssertTrue((note.value as? String ?? "").contains("unsaved here"))
        let medicine = app.textFields["Medicine name"]; reveal(medicine, app)
        XCTAssertEqual(medicine.value as? String, "Synthetic medicine")
        let details = app.buttons["migraine-history-save"]; reveal(details, app); details.tap()
        let status = app.staticTexts["migraine-history-status"]; reveal(status, app)
        XCTAssertEqual(status.label, "Migraine details saved.")
    }

    @MainActor func testTimeSaveLocksRecreatedSeverityNoteAndTimeControls() {
        let app = launch("time-delayed-history")
        let note = app.textFields["migraine-history-note"]
        XCTAssertTrue(note.waitForExistence(timeout: 8)); start(app); save(app)
        XCTAssertEqual(app.staticTexts["migraine-fixture-save-state"].label, "Save pending")
        let date = app.textFields["migraine-time-start-date"]; reveal(date, app, up: true)
        let value = date.value as? String
        date.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertFalse(app.keyboards.firstMatch.exists); XCTAssertEqual(date.value as? String, value)
        reveal(note, app, up: true)
        note.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap(); XCTAssertFalse(app.keyboards.firstMatch.exists)
        let severity = app.steppers["migraine-history-severity"]; reveal(severity, app, up: true)
        let original = severity.label
        for button in severity.buttons.allElementsBoundByIndex {
            button.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
            XCTAssertEqual(severity.label, original)
        }
        screenshot(app, "G013 pending time save locks recreated original controls")
        app.buttons["migraine-release-response"].tap()
        XCTAssertEqual(message(app).label, "Migraine times saved.")
        reveal(severity, app, up: true); severity.buttons.element(boundBy: 0).tap(); XCTAssertNotEqual(severity.label, original)
    }

    @MainActor func testOtherSaveLocksTimeControlsAndRequiresExplicitRebase() {
        let app = launch("time-delayed-history")
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 8)); start(app)
        let saveOther = app.buttons["migraine-history-legacy-save"]; reveal(saveOther, app); saveOther.tap()
        let date = app.textFields["migraine-time-start-date"]; reveal(date, app, up: true)
        XCTAssertEqual(app.staticTexts["migraine-fixture-save-state"].label, "Save pending")
        let original = date.value as? String
        date.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertFalse(app.keyboards.firstMatch.exists); XCTAssertEqual(date.value as? String, original)
        app.buttons["migraine-release-response"].tap()
        XCTAssertTrue(message(app).label.contains("Other details were saved"))
        app.buttons["migraine-time-reload"].tap(); save(app)
        XCTAssertEqual(message(app).label, "Migraine times saved.")
    }

    @MainActor func testDelayedAccountChangeHidesOldEditor() {
        let app = launch("time-delayed-account-history")
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 8)); start(app); save(app)
        app.buttons["Switch synthetic account"].tap(); app.buttons["migraine-release-response"].tap()
        XCTAssertTrue(app.staticTexts["Your signed-in account changed. Close this editor and open it again."].waitForExistence(timeout: 8))
        XCTAssertFalse(app.textFields["migraine-history-note"].exists)
        XCTAssertFalse(app.staticTexts["Migraine times saved."].exists)
    }
    @MainActor func testCancelledResponseRetainsRetryAndEndClearKeepsResolvedState() {
        let app = launch("time-history-cancelled")
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 8))
        let end = app.buttons["migraine-time-end-mode"]; reveal(end, app); end.tap(); app.buttons["End unknown"].tap()
        save(app); XCTAssertTrue(message(app).label.contains("could not be confirmed"))
        save(app); XCTAssertEqual(message(app).label, "Migraine times saved.")
        let savedEnd = app.staticTexts["migraine-time-saved-end"]; reveal(savedEnd, app, up: true)
        XCTAssertEqual(savedEnd.label, "Saved end: End unknown")
        let state = app.buttons["migraine-time-state"]; reveal(state, app)
        XCTAssertTrue(state.label.contains("resolved"))
        state.tap(); app.buttons["Ongoing"].tap(); save(app)
        XCTAssertEqual(message(app).label, "Migraine times saved.")
        reveal(state, app, up: true); XCTAssertTrue(state.label.contains("ongoing"))
        screenshot(app, "G013 explicit unknown end and deliberate reopening")
    }

    @MainActor func testTimeSaveProtectsCalendarDoneUntilAcknowledgement() {
        let app = launch("calendar-time-delayed")
        XCTAssertTrue(app.staticTexts["migraine-calendar-count"].waitForExistence(timeout: 10))
        let episode = app.buttons["migraine-calendar-episode-33333333-3333-4333-8333-333333333333"]
        reveal(episode, app); episode.tap()
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 8)); start(app); save(app)
        XCTAssertFalse(app.buttons["migraine-calendar-editor-done"].isEnabled)
        app.buttons["migraine-calendar-release-save"].tap()
        XCTAssertEqual(message(app).label, "Migraine times saved.")
        XCTAssertTrue(app.buttons["migraine-calendar-editor-done"].isEnabled)
    }

}
