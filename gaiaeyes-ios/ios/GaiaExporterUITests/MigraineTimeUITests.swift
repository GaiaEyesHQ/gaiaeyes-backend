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
        for _ in 0..<24 {
            let navigation = app.navigationBars["Edit symptom"].exists ? app.navigationBars["Edit symptom"] : app.navigationBars.firstMatch
            let top = navigation.exists ? navigation.frame.maxY + 4 : 120
            let bottom = app.keyboards.firstMatch.exists ? app.keyboards.firstMatch.frame.minY - 45 : app.frame.maxY - 35
            let frame = element.exists ? element.frame : .zero
            // XCTest sometimes calls controls below the keyboard or partly
            // behind the navigation bar hittable. Require visible bounds too.
            if element.exists && element.isHittable && frame.minY >= top && frame.maxY <= bottom { return }
            let towardTop = element.exists && frame != .zero
                ? frame.midY < top : up
            // Drag in the Form's outer gutter. Dragging across the active note
            // field selects text and opens its edit menu instead of scrolling.
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: towardTop ? 0.25 : 0.46))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: towardTop ? 0.62 : 0.18)))
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
    @MainActor private func start(_ app: XCUIApplication, date: String = "2026-08-31", up: Bool = false) {
        let toggle = app.switches["migraine-time-start-mode"]; reveal(toggle, app, up: up)
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

    @MainActor private func addEdit(_ element: XCUIElement, text: String, _ app: XCUIApplication, up: Bool = false) -> String {
        reveal(element, app, up: up)
        let before = element.value as? String ?? ""
        element.tap(); element.typeText(text)
        let intended = element.value as? String ?? ""
        // A real edit at the user's caret position; later checks compare this
        // exact intended value through all three acknowledgements.
        XCTAssertNotEqual(intended, before); XCTAssertTrue(intended.contains(text))
        return intended
    }

    @MainActor private func changedNoteTimeMedicineSequence(_ app: XCUIApplication) -> (note: String, medicine: String) {
        let note = app.textFields["migraine-history-note"]
        XCTAssertTrue(note.waitForExistence(timeout: 8))
        let intendedNote = addEdit(note, text: "Changed legacy note ", app)
        let medicine = app.textFields["Medicine name"]
        let intendedMedicine = addEdit(medicine, text: "Intended ", app)
        start(app, up: true)
        let legacy = app.buttons["migraine-history-legacy-save"]; reveal(legacy, app); legacy.tap()
        let status = app.staticTexts["migraine-history-legacy-status"]; reveal(status, app)
        XCTAssertEqual(status.label, "Changes saved.")
        let timeMessage = app.staticTexts["migraine-time-message"]; reveal(timeMessage, app, up: true)
        XCTAssertTrue(timeMessage.label.contains("Other details were saved"))
        app.buttons["migraine-time-reload"].tap(); save(app)
        XCTAssertEqual(message(app).label, "Migraine times saved.")
        reveal(medicine, app); XCTAssertEqual(medicine.value as? String, intendedMedicine)
        return (intendedNote, intendedMedicine)
    }

    @MainActor func testChangedLegacyNoteThenTimeThenMedicineSave() {
        let app = launch("time-history-success")
        let intended = changedNoteTimeMedicineSequence(app)
        let details = app.buttons["migraine-history-save"]; reveal(details, app); details.tap()
        let status = app.staticTexts["migraine-history-status"]; reveal(status, app)
        XCTAssertEqual(status.label, "Migraine details saved.")
        let note = app.textFields["migraine-history-note"]; reveal(note, app, up: true)
        XCTAssertEqual(note.value as? String, intended.note.trimmingCharacters(in: .whitespacesAndNewlines))
        let medicine = app.textFields["Medicine name"]; reveal(medicine, app)
        XCTAssertEqual(medicine.value as? String, intended.medicine.trimmingCharacters(in: .whitespacesAndNewlines))
        screenshot(app, "G-R22 changed note time medicine save acknowledged")
        reveal(details, app); details.tap(); reveal(status, app)
        XCTAssertEqual(status.label, "No migraine detail changes to save.")
    }

    @MainActor func testExternalDetailConflictCanReloadAndKeepIntendedEditsInEditor() {
        let app = launch("time-history-external-details")
        let intended = changedNoteTimeMedicineSequence(app)
        let note = app.textFields["migraine-history-note"]
        let intendedNote = addEdit(note, text: "Still intended ", app, up: true)
        let details = app.buttons["migraine-history-save"]; reveal(details, app); details.tap()
        let status = app.staticTexts["migraine-history-status"]; reveal(status, app)
        XCTAssertTrue(status.label.contains("Your changes are still here"))
        XCTAssertFalse(details.isEnabled)
        let reload = app.buttons["migraine-history-reload"]; reveal(reload, app)
        screenshot(app, "G-R22 explicit recovery from intervening external detail edit")
        reload.tap(); reveal(status, app)
        XCTAssertTrue(status.label.contains("Saved details reloaded"))
        reveal(note, app, up: true); XCTAssertEqual(note.value as? String, intendedNote)
        let medicine = app.textFields["Medicine name"]; reveal(medicine, app)
        XCTAssertEqual(medicine.value as? String, intended.medicine)
        reveal(details, app); XCTAssertTrue(details.isEnabled); details.tap(); reveal(status, app)
        XCTAssertEqual(status.label, "Migraine details saved.")
        screenshot(app, "G-R22 medicine and note intent saved after explicit recovery")
        reveal(details, app); details.tap(); reveal(status, app)
        XCTAssertEqual(status.label, "No migraine detail changes to save.")
    }

    @MainActor func testDelayedAccountChangeHidesOldEditor() {
        let app = launch("time-delayed-account-history")
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 8)); start(app); save(app)
        app.buttons["Switch synthetic account"].tap(); app.buttons["migraine-release-response"].tap()
        XCTAssertTrue(app.staticTexts["Your signed-in account changed. Close this editor and open it again."].waitForExistence(timeout: 8))
        XCTAssertFalse(app.textFields["migraine-history-note"].exists)
        XCTAssertFalse(app.staticTexts["Migraine times saved."].exists)
    }

    @MainActor private func prepareAddedMedicine(_ app: XCUIApplication, validateEmpty: Bool = false) {
        XCTAssertTrue(app.textFields["migraine-history-note"].waitForExistence(timeout: 8))
        let choice = app.buttons["migraine-medicine-choice"]; reveal(choice, app); choice.tap()
        if validateEmpty {
            let save = app.buttons["migraine-history-save"]; reveal(save, app); save.tap()
            let status = app.staticTexts["migraine-history-status"]; reveal(status, app)
            XCTAssertTrue(status.label.contains("Add the medicine name"))
            XCTAssertFalse(app.buttons["migraine-history-reload"].exists)
            XCTAssertEqual(save.label, "Save migraine details")
        }
        let name = app.textFields["Medicine name"]; reveal(name, app, up: validateEmpty)
        name.tap(); name.typeText("Synthetic medicine") // Legitimate repeated name: never deduplicate it.
    }
    @MainActor private func saveDetailsAndStatus(_ app: XCUIApplication) -> XCUIElement {
        let save = app.buttons["migraine-history-save"]; reveal(save, app); XCTAssertTrue(save.isEnabled); save.tap()
        let status = app.staticTexts["migraine-history-status"]; reveal(status, app); return status
    }
    @MainActor private func assertSavedMedicineCount(_ count: Int, _ app: XCUIApplication) {
        let summary = app.staticTexts["migraine-saved-medicine-summary"]; reveal(summary, app, up: true)
        XCTAssertTrue(summary.label.hasPrefix("\(count) saved medicine entries."), summary.label)
    }

    @MainActor func testCommittedMedicineResponseLossRetriesWithoutDuplicateAndLocksOtherInputs() {
        let app = launch("time-history-detail-lost")
        prepareAddedMedicine(app, validateEmpty: true)
        XCTAssertTrue(saveDetailsAndStatus(app).label.contains("could not be confirmed"))
        XCTAssertEqual(app.buttons["migraine-history-save"].label, "Retry same migraine save")
        XCTAssertFalse(app.buttons["migraine-history-reload"].exists)
        XCTAssertEqual(app.staticTexts["migraine-fixture-save-state"].label, "Save pending")
        screenshot(app, "G-R23 exact retry offered after committed medicine response loss")
        let legacy = app.buttons["migraine-history-legacy-save"]; reveal(legacy, app); XCTAssertFalse(legacy.isEnabled)
        let medicine = app.textFields["Medicine name"]; reveal(medicine, app, up: true)
        let intended = medicine.value as? String
        medicine.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertFalse(app.keyboards.firstMatch.exists); XCTAssertEqual(medicine.value as? String, intended)
        let toggle = app.switches["migraine-time-start-mode"]; reveal(toggle, app, up: true); XCTAssertFalse(toggle.isEnabled)
        let note = app.textFields["migraine-history-note"]; reveal(note, app, up: true)
        note.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap(); XCTAssertFalse(app.keyboards.firstMatch.exists)
        XCTAssertEqual(saveDetailsAndStatus(app).label, "Migraine details saved.")
        XCTAssertEqual(app.staticTexts["migraine-fixture-save-state"].label, "Save idle")
        assertSavedMedicineCount(2, app)
        screenshot(app, "G-R23 one addition after exact retry including repeated medicine name")
        XCTAssertEqual(saveDetailsAndStatus(app).label, "No migraine detail changes to save.")
    }

    @MainActor func testMedicineFailureBeforeCommitCanRetrySameSave() {
        let app = launch("time-history-detail-before")
        prepareAddedMedicine(app)
        XCTAssertTrue(saveDetailsAndStatus(app).label.contains("could not be confirmed"))
        XCTAssertEqual(saveDetailsAndStatus(app).label, "Migraine details saved.")
        assertSavedMedicineCount(2, app)
        XCTAssertEqual(saveDetailsAndStatus(app).label, "No migraine detail changes to save.")
    }

    @MainActor func testGenuineExternalConflictRebasesOneUncommittedAddition() {
        let app = launch("time-history-external-details")
        prepareAddedMedicine(app)
        XCTAssertTrue(saveDetailsAndStatus(app).label.contains("reload and review"))
        let reload = app.buttons["migraine-history-reload"]; reveal(reload, app); reload.tap()
        let status = app.staticTexts["migraine-history-status"]; reveal(status, app, up: true)
        XCTAssertTrue(status.label.contains("Saved details reloaded"))
        XCTAssertEqual(saveDetailsAndStatus(app).label, "Migraine details saved.")
        assertSavedMedicineCount(3, app) // Original + genuine external addition + one intended addition.
    }

    @MainActor func testLaterExternalEditRequiresDeliberateReviewWithoutReappending() {
        let app = launch("time-history-detail-lost-later")
        prepareAddedMedicine(app)
        XCTAssertTrue(saveDetailsAndStatus(app).label.contains("could not be confirmed"))
        XCTAssertTrue(saveDetailsAndStatus(app).label.contains("could not be confirmed"))
        XCTAssertFalse(app.buttons["migraine-history-reload"].exists)
        let review = app.buttons["migraine-history-review-uncertain"]; reveal(review, app); review.tap()
        let use = app.buttons["migraine-history-use-reviewed"]; reveal(use, app)
        XCTAssertEqual(app.staticTexts["migraine-fixture-save-state"].label, "Save pending")
        screenshot(app, "G-R23 later external change requires explicit saved-version decision")
        use.tap()
        // Removing the expanded review sections returns this Form to the top.
        let status = app.staticTexts["migraine-history-status"]; reveal(status, app)
        XCTAssertTrue(status.label.contains("no new save was sent"))
        assertSavedMedicineCount(2, app)
        screenshot(app, "G-R23 reviewed saved version retains exactly two medicines")
        XCTAssertEqual(saveDetailsAndStatus(app).label, "No migraine detail changes to save.")
    }

    @MainActor func testAccountChangeClearsUncertainMedicineEditorWithoutSendingRetry() {
        let app = launch("time-history-detail-account-detail-lost")
        prepareAddedMedicine(app)
        XCTAssertTrue(saveDetailsAndStatus(app).label.contains("could not be confirmed"))
        app.buttons["Switch synthetic account"].tap()
        XCTAssertTrue(app.staticTexts["Your signed-in account changed. Close this editor and open it again."].waitForExistence(timeout: 8))
        XCTAssertFalse(app.buttons["migraine-history-save"].exists)
        XCTAssertEqual(app.staticTexts["migraine-fixture-save-state"].label, "Save idle")
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
