import XCTest

final class MigraineEpisodeSummaryUITests: XCTestCase {
    private let first = "11111111-1111-4111-8111-111111111111"
    private let second = "33333333-3333-4333-8333-333333333333"
    override func setUpWithError() throws { continueAfterFailure = false }

    @MainActor private func launch(_ scenario: String, enabled: Bool = true) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-gaia-preview-migraine-follow-up-fixture", "-gaia-enable-structured-migraine-follow-up",
                               "-gaia-migraine-scenario", scenario]
        if enabled { app.launchArguments.append("-gaia-enable-migraine-calendar") }
        app.launch()
        XCTAssertTrue(app.staticTexts["migraine-calendar-count"].waitForExistence(timeout: 10))
        return app
    }
    @MainActor private func reveal(_ item: XCUIElement, _ app: XCUIApplication, up: Bool = false) {
        for _ in 0..<24 {
            let bar = app.navigationBars.firstMatch
            let top = bar.exists ? bar.frame.maxY + 4 : 120
            let bottom = app.keyboards.firstMatch.exists ? app.keyboards.firstMatch.frame.minY - 40 : app.frame.maxY - 45
            let frame = item.exists ? item.frame : .zero
            if item.exists && item.isHittable && frame.minY >= top && (frame.maxY <= bottom || frame.height > bottom-top) { return }
            let towardTop = item.exists && frame != .zero ? frame.midY < top : up
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: towardTop ? 0.25 : 0.46))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: towardTop ? 0.62 : 0.18)))
        }
        XCTAssertTrue(item.isHittable, item.debugDescription)
    }
    @MainActor private func openSummary(_ id: String, _ app: XCUIApplication) {
        let action = app.buttons["migraine-calendar-summary-\(id)"]; reveal(action, app); action.tap()
    }
    @MainActor private func saved(_ app: XCUIApplication) {
        XCTAssertTrue(app.staticTexts["migraine-summary-saved"].waitForExistence(timeout: 10))
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let item = XCTAttachment(screenshot: app.screenshot()); item.name = name; item.lifetime = .keepAlways; add(item)
    }
    @MainActor private func assertCompleteNotes(_ app: XCUIApplication) {
        let notes = app.staticTexts["migraine-summary-notes"]; reveal(notes, app)
        XCTAssertTrue(notes.label.contains("Saved summary opening paragraph."))
        XCTAssertTrue(notes.label.hasSuffix("Saved summary final paragraph — the full note is visible at the end."))
        app.swipeUp(); app.swipeUp()
        capture(app, "G016 full saved note final paragraph")
    }

    @MainActor func testCompleteSavedSummaryAndReturnPreserveSelectedDay() {
        let app = launch("calendar-summary-full")
        app.buttons["migraine-calendar-day-2026-09-08"].tap()
        let day = app.staticTexts["migraine-calendar-selected-day"].label
        let month = app.staticTexts["migraine-calendar-month"].label
        openSummary(second, app); saved(app)
        XCTAssertTrue(app.staticTexts["migraine-summary-start-line-0"].label.contains("11:30:00 PM"))
        XCTAssertTrue(app.staticTexts["migraine-summary-end-line-0"].label.contains("2:30:00 AM"))
        XCTAssertEqual(app.staticTexts["migraine-summary-duration-line-0"].label, "3 hours")
        capture(app, "G016 saved canonical timing and display timezone")
        let dose = app.staticTexts["migraine-summary-medicine-1-line-1"]; reveal(dose, app)
        XCTAssertEqual(dose.label, "Dose: 2.500000000000000001 mg")
        XCTAssertEqual(app.staticTexts["migraine-summary-medicine-1-title"].label, "2. Test medicine")
        XCTAssertEqual(app.staticTexts["migraine-summary-medicine-1-line-2"].label, "Reported relief: Not sure yet")
        capture(app, "G016 repeated medicine exact dose and unknown relief")
        let absent = app.staticTexts["migraine-summary-medicine-2-line-2"]; reveal(absent, app)
        XCTAssertEqual(absent.label, "Reported relief: Not recorded")
        let none = app.staticTexts["migraine-summary-medicine-3-line-2"]; reveal(none, app)
        XCTAssertEqual(none.label, "Reported relief: No relief")
        assertCompleteNotes(app)
        app.buttons["migraine-summary-done"].tap()
        XCTAssertEqual(app.staticTexts["migraine-calendar-selected-day"].label, day)
        XCTAssertEqual(app.staticTexts["migraine-calendar-month"].label, month)
        XCTAssertEqual(app.staticTexts["migraine-calendar-count"].label, "1 migraine episode")
    }

    @MainActor func testMissingFieldsStayUnanswered() {
        let app = launch("calendar-summary-empty"); openSummary(first, app); saved(app)
        XCTAssertEqual(app.staticTexts["migraine-summary-end-line-0"].label, "Not recorded")
        XCTAssertEqual(app.staticTexts["migraine-summary-severity-line-0"].label, "Not recorded")
        let medicines = app.staticTexts["migraine-summary-medicines-empty"]; reveal(medicines, app)
        XCTAssertEqual(medicines.label, "No medicine entries recorded")
        XCTAssertFalse(app.staticTexts["No medicine taken"].exists)
        XCTAssertFalse(app.staticTexts["migraine-summary-medicine-0-title"].exists)
        XCTAssertEqual(app.staticTexts["migraine-summary-signs-empty"].label, "Not recorded")
        XCTAssertEqual(app.staticTexts["migraine-summary-contexts-empty"].label, "Not recorded")
        let notes = app.staticTexts["migraine-summary-notes"]; reveal(notes, app)
        XCTAssertEqual(notes.label, "Not recorded")
        capture(app, "G016 honest missing saved information")
    }

    @MainActor func testOrdinarySavedEpisodeOpensWithoutStructuredDetails() {
        let app = launch("calendar-summary-unstructured")
        let day = app.staticTexts["migraine-calendar-selected-day"].label
        openSummary(first, app); saved(app)
        XCTAssertEqual(app.staticTexts["migraine-summary-severity-line-0"].label, "5/10")
        XCTAssertEqual(app.staticTexts["migraine-summary-end-line-0"].label, "Not recorded")
        let medicine = app.staticTexts["migraine-summary-medicines-empty"]; reveal(medicine, app)
        XCTAssertEqual(medicine.label, "No medicine entries recorded")
        let notes = app.staticTexts["migraine-summary-notes"]; reveal(notes, app)
        XCTAssertEqual(notes.label, "Saved manual migraine note.")
        XCTAssertFalse(app.staticTexts["migraine-summary-updated"].exists)
        capture(app, "G016 ordinary saved episode without structured rows")
        app.buttons["migraine-summary-done"].tap()
        XCTAssertEqual(app.staticTexts["migraine-calendar-selected-day"].label, day)
    }

    @MainActor func testUnavailableThenRetryReadsSavedDetails() {
        let app = launch("calendar-summary-retry"); openSummary(first, app)
        let error = app.staticTexts["migraine-summary-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 10))
        XCTAssertTrue(error.label.contains("not available on this server"))
        XCTAssertFalse(app.staticTexts["migraine-summary-saved"].exists)
        capture(app, "G016 unavailable is not an empty report")
        app.buttons["migraine-summary-retry"].tap(); saved(app)
        XCTAssertFalse(error.exists)
    }

    @MainActor func testMalformedReplyCannotDisplayASavedSummary() {
        let app = launch("calendar-summary-malformed"); openSummary(first, app)
        XCTAssertTrue(app.staticTexts["migraine-summary-error"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["migraine-summary-saved"].exists)
        XCTAssertFalse(app.staticTexts["migraine-summary-medicines-empty"].exists)
    }

    @MainActor func testAccountChangeRejectsDelayedSummary() {
        let app = launch("calendar-summary-account"); openSummary(first, app)
        XCTAssertTrue(app.staticTexts["migraine-summary-loading"].waitForExistence(timeout: 10))
        app.buttons["migraine-summary-fixture-account"].tap()
        XCTAssertTrue(app.staticTexts["No migraine episodes recorded for this day."].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["migraine-summary-saved"].exists)
        XCTAssertFalse(app.staticTexts["migraine-summary-medicine-0-title"].exists)
        capture(app, "G016 changed account hides delayed saved summary")
    }

    @MainActor func testLargeTextKeepsExactDoseAndCompleteNotesReadable() {
        let app = launch("calendar-summary-large"); openSummary(second, app); saved(app)
        capture(app, "G016 saved summary at accessibility3 text size")
        let dose = app.staticTexts["migraine-summary-medicine-1-line-1"]; reveal(dose, app)
        XCTAssertEqual(dose.label, "Dose: 2.500000000000000001 mg")
        capture(app, "G016 exact supported dose at large text size")
        assertCompleteNotes(app)
    }

    @MainActor func testAcknowledgedEditorNoteAppearsOnlyAfterReopeningSavedSummary() {
        let app = launch("calendar-summary-edit"); openSummary(second, app); saved(app)
        XCTAssertFalse(app.staticTexts["migraine-summary-updated"].exists)
        app.buttons["migraine-summary-done"].tap()
        let editor = app.buttons["migraine-calendar-episode-\(second)"]; reveal(editor, app); editor.tap()
        let note = app.textFields["migraine-history-note"]
        XCTAssertTrue(note.waitForExistence(timeout: 10)); let old = note.value as? String ?? ""
        note.tap(); note.press(forDuration: 1.0)
        let intended = "G016 acknowledged saved episode note."
        let selectAll = app.menuItems["Select All"].exists ? app.menuItems["Select All"] : app.buttons["Select All"]
        if selectAll.waitForExistence(timeout: 2) { selectAll.tap(); note.typeText(intended) }
        else {
            note.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.5)).tap()
            note.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: old.count) + intended)
        }
        XCTAssertEqual(note.value as? String, intended)
        let save = app.buttons["migraine-history-legacy-save"]; reveal(save, app); save.tap()
        let status = app.staticTexts["migraine-history-legacy-status"]; reveal(status, app)
        XCTAssertEqual(status.label, "Changes saved.")
        app.buttons["migraine-calendar-editor-done"].tap()
        openSummary(second, app); saved(app)
        XCTAssertFalse(app.staticTexts["migraine-summary-updated"].exists)
        let savedNote = app.staticTexts["migraine-summary-notes"]; reveal(savedNote, app)
        XCTAssertEqual(savedNote.label, intended)
        capture(app, "G016 reopened summary reads acknowledged canonical note")
    }

    @MainActor func testSummaryEntryRemainsDefaultOff() {
        let app = launch("calendar-summary-gated", enabled: false)
        XCTAssertFalse(app.buttons["migraine-calendar-summary-\(first)"].exists)
        XCTAssertFalse(app.buttons["migraine-calendar-summary-\(second)"].exists)
        XCTAssertFalse(app.staticTexts["migraine-summary-saved"].exists)
    }
}
