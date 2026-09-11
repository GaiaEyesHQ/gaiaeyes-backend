import XCTest

final class MigraineMedicineEntryUITests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }
    @MainActor private func launch(_ scenario: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-gaia-preview-migraine-follow-up-fixture", "-gaia-enable-structured-migraine-follow-up",
            "-gaia-enable-migraine-time-editing", "-gaia-migraine-scenario", scenario]
        app.launch()
        let initial = scenario.contains("history") ? app.textFields["migraine-history-note"] : app.textFields["Early signs, separated by commas"]
        XCTAssertTrue(initial.waitForExistence(timeout: 10))
        return app
    }
    @MainActor private func reveal(_ element: XCUIElement, _ app: XCUIApplication, up: Bool = false) {
        for _ in 0..<24 {
            let navigation = app.navigationBars.firstMatch
            let top = navigation.exists ? navigation.frame.maxY + 4 : 120
            let bottom = app.keyboards.firstMatch.exists ? app.keyboards.firstMatch.frame.minY - 45 : app.frame.maxY - 35
            let frame = element.exists ? element.frame : .zero
            if element.exists && element.isHittable && frame.minY >= top && frame.maxY <= bottom { return }
            let towardTop = element.exists && frame != .zero ? frame.midY < top : up
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: towardTop ? 0.25 : 0.46))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: towardTop ? 0.62 : 0.18)))
        }
        XCTAssertTrue(element.isHittable, element.debugDescription)
    }
    @MainActor private func select(_ index: Int, _ app: XCUIApplication, up: Bool = true) {
        let row = app.buttons["migraine-medicine-entry-\(index)"]; reveal(row, app, up: up); row.tap()
    }
    @MainActor private func fill(_ field: XCUIElement, _ text: String, _ app: XCUIApplication) {
        reveal(field, app)
        let old = field.value as? String ?? ""
        field.tap()
        if old != field.placeholderValue && !old.isEmpty {
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
    @MainActor private func add(_ name: String, _ app: XCUIApplication) {
        let add = app.buttons["migraine-medicine-choice"]; reveal(add, app, up: true); add.tap()
        fill(app.textFields["Medicine name"], name, app)
    }
    @MainActor private func save(_ app: XCUIApplication, history: Bool) {
        let save = app.buttons[history ? "migraine-history-save" : "migraine-save-response"]
        reveal(save, app); XCTAssertTrue(save.isEnabled); save.tap()
    }
    @MainActor private func status(_ app: XCUIApplication, history: Bool) -> XCUIElement {
        let status = app.staticTexts[history ? "migraine-history-status" : "migraine-save-error"]
        reveal(status, app); return status
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot()); image.name = name; image.lifetime = .keepAlways; add(image)
    }
    @MainActor private func assertDraftCount(_ count: Int, _ app: XCUIApplication) {
        let summary = app.staticTexts["migraine-saved-medicine-summary"]; reveal(summary, app, up: true)
        XCTAssertTrue(summary.label.contains("\(count) entries in this draft"), summary.label)
    }
    @MainActor private func assertListLocked(_ app: XCUIApplication, expectedName: String, count: Int) {
        let first = app.buttons["migraine-medicine-entry-1"]; reveal(first, app, up: true)
        XCTAssertFalse(first.isEnabled)
        first.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        let add = app.buttons["migraine-medicine-choice"]; reveal(add, app)
        XCTAssertFalse(add.isEnabled); add.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        let clear = app.buttons["migraine-medicine-clear"]; XCTAssertFalse(clear.isEnabled)
        let name = app.textFields["Medicine name"]; reveal(name, app)
        XCTAssertFalse(name.isEnabled); XCTAssertEqual(name.value as? String, expectedName)
        let remove = app.buttons["migraine-medicine-remove"]; reveal(remove, app)
        XCTAssertFalse(remove.isEnabled); remove.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        assertDraftCount(count, app)
    }

    @MainActor func testHistoryEditsMiddleAndLastAddsTwoRemovesOneAndCorrectsInvalidFields() {
        let app = launch("time-history-entries-success")
        select(2, app, up: false)
        fill(app.textFields["Dose"], "2oops", app)
        select(3, app)
        fill(app.textFields["migraine-medicine-note"], "Edited third entry", app)
        save(app, history: true)
        XCTAssertTrue(status(app, history: true).label.contains("dose"))
        select(2, app); XCTAssertEqual(app.textFields["Dose"].value as? String, "2oops")
        fill(app.textFields["Dose"], "2.500000000000000001", app)
        let relief = app.buttons["migraine-medicine-relief"]; reveal(relief, app); relief.tap(); app.buttons["No relief"].tap()
        add("Added one", app); add("Added two", app)
        select(1, app)
        let remove = app.buttons["migraine-medicine-remove"]; reveal(remove, app); remove.tap()
        assertDraftCount(4, app)
        capture(app, "G014 history ordered draft after middle-last edits two adds and one removal")
        save(app, history: true); XCTAssertEqual(status(app, history: true).label, "Migraine details saved.")
        assertDraftCount(4, app)
        capture(app, "G014 history acknowledgement retains four entries")
    }

    @MainActor func testFollowUpEditsLastAndAddsTwoDistinctEntries() {
        let app = launch("entries-success")
        select(3, app, up: false)
        fill(app.textFields["migraine-medicine-note"], "Edited last from follow-up", app)
        add("Repeated new medicine", app); add("Repeated new medicine", app)
        select(2, app)
        let remove = app.buttons["migraine-medicine-remove"]; reveal(remove, app); remove.tap()
        assertDraftCount(4, app)
        capture(app, "G014 follow-up draft retains distinct repeated medicines")
        save(app, history: false)
        XCTAssertTrue(app.staticTexts["migraine-confirmed"].waitForExistence(timeout: 8))
    }

    @MainActor func testHistoryLostResponseLocksEveryListActionUntilExactRetry() {
        let app = launch("time-history-entries-detail-lost")
        add("Uncertain new entry", app)
        save(app, history: true)
        XCTAssertTrue(status(app, history: true).label.contains("could not be confirmed"))
        assertListLocked(app, expectedName: "Uncertain new entry", count: 4)
        capture(app, "G014 history uncertain request locks list identity and actions")
        save(app, history: true); XCTAssertEqual(status(app, history: true).label, "Migraine details saved.")
        assertDraftCount(4, app)
        select(3, app); let name = app.textFields["Medicine name"]; reveal(name, app); XCTAssertTrue(name.isEnabled)
    }

    @MainActor func testFollowUpLostResponseLocksWholeResponseUntilIdenticalRetry() {
        let app = launch("entries-committed-timeout")
        add("Uncertain follow-up entry", app)
        save(app, history: false)
        XCTAssertTrue(status(app, history: false).label.contains("could not be confirmed"))
        assertListLocked(app, expectedName: "Uncertain follow-up entry", count: 4)
        let note = app.textViews["migraine-episode-note"]; reveal(note, app); XCTAssertFalse(note.isEnabled)
        capture(app, "G014 follow-up exact retry keeps the full response locked")
        save(app, history: false)
        XCTAssertTrue(app.staticTexts["migraine-confirmed"].waitForExistence(timeout: 8))
    }

    @MainActor func testHistoryCancellationAfterHeldCommitRetriesWithoutDuplicate() {
        let app = launch("time-history-entries-time-delayed-detail-cancelled")
        add("Cancelled history entry", app); save(app, history: true)
        assertListLocked(app, expectedName: "Cancelled history entry", count: 4)
        app.buttons["migraine-release-response"].tap()
        XCTAssertTrue(status(app, history: true).label.contains("could not be confirmed"))
        save(app, history: true); XCTAssertEqual(status(app, history: true).label, "Migraine details saved.")
        assertDraftCount(4, app)
    }

    @MainActor func testFollowUpHeldCancellationKeepsPendingEntriesForRetry() {
        let app = launch("delayed-entries-follow-up-cancelled")
        add("Cancelled follow-up entry", app); save(app, history: false)
        assertListLocked(app, expectedName: "Cancelled follow-up entry", count: 4)
        app.buttons["migraine-release-response"].tap()
        XCTAssertTrue(status(app, history: false).label.contains("could not be confirmed"))
        save(app, history: false)
        XCTAssertTrue(app.staticTexts["migraine-confirmed"].waitForExistence(timeout: 8))
    }

    @MainActor func testFollowUpDefinitiveConflictReloadPreservesMiddleEditAndNewEntry() {
        let app = launch("entries-conflict-once")
        select(2, app, up: false); fill(app.textFields["migraine-medicine-note"], "My middle edit", app)
        add("My new entry", app); save(app, history: false)
        XCTAssertTrue(status(app, history: false).label.contains("changed"))
        let reload = app.buttons["migraine-followup-reload"]; reveal(reload, app, up: true); reload.tap()
        XCTAssertTrue(status(app, history: false).label.contains("reloaded"))
        assertDraftCount(4, app); select(2, app)
        let note = app.textFields["migraine-medicine-note"]; reveal(note, app); XCTAssertEqual(note.value as? String, "My middle edit")
        save(app, history: false)
        XCTAssertTrue(app.staticTexts["migraine-confirmed"].waitForExistence(timeout: 8))
    }

    @MainActor func testTimeSaveKeepsUnsavedMiddleAndAddedEntriesAndLocksList() {
        let app = launch("time-history-entries-time-delayed-success")
        select(2, app, up: false); fill(app.textFields["migraine-medicine-note"], "Middle before time save", app)
        add("Added before time save", app)
        let toggle = app.switches["migraine-time-start-mode"]; reveal(toggle, app, up: true)
        toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)).tap()
        fill(app.textFields["migraine-time-start-date"], "2026-08-31", app)
        let saveTime = app.buttons["migraine-time-save"]; reveal(saveTime, app); saveTime.tap()
        assertListLocked(app, expectedName: "Added before time save", count: 4)
        app.buttons["migraine-release-response"].tap()
        let message = app.staticTexts["migraine-time-message"]; reveal(message, app, up: true)
        XCTAssertEqual(message.label, "Migraine times saved.")
        assertDraftCount(4, app); select(2, app)
        let note = app.textFields["migraine-medicine-note"]; reveal(note, app); XCTAssertEqual(note.value as? String, "Middle before time save")
        save(app, history: true); XCTAssertEqual(status(app, history: true).label, "Migraine details saved.")
        assertDraftCount(4, app)
    }

    @MainActor private func accountDuringHeldSave(history: Bool) {
        let app = launch(history ? "time-history-entries-time-delayed-account-detail-lost" : "delayed-entries-account-success")
        add("Old account draft", app); save(app, history: history)
        app.buttons["Switch synthetic account"].tap()
        app.buttons["migraine-release-response"].tap()
        let error = app.staticTexts[history ? "Your signed-in account changed. Close this editor and open it again." : "migraine-save-error"]
        reveal(error, app); XCTAssertTrue(error.label.contains("account changed"))
        XCTAssertFalse(app.buttons["migraine-medicine-choice"].exists)
        XCTAssertFalse(app.staticTexts["migraine-confirmed"].exists)
    }
    @MainActor func testHistoryAccountChangeHidesPendingMedicineRows() { accountDuringHeldSave(history: true) }
    @MainActor func testFollowUpAccountChangeHidesPendingMedicineRows() { accountDuringHeldSave(history: false) }

    @MainActor func testHistoryMissingNameCanBeCorrectedWithoutReload() {
        let app = launch("time-history-entries-name-validation")
        let add = app.buttons["migraine-medicine-choice"]; reveal(add, app); add.tap()
        save(app, history: true)
        XCTAssertTrue(status(app, history: true).label.contains("name"))
        XCTAssertFalse(app.buttons["migraine-history-reload"].exists)
        let name = app.textFields["Medicine name"]; reveal(name, app, up: true); XCTAssertTrue(name.isEnabled)
        fill(name, "Corrected new name", app)
        save(app, history: true); XCTAssertEqual(status(app, history: true).label, "Migraine details saved.")
        assertDraftCount(4, app)
    }

    @MainActor func testHistoryAmbiguousEntryRequiresExplicitSavedVersionDecision() {
        let app = launch("time-history-entries-external-details-ambiguous-entry")
        select(2, app, up: false); fill(app.textFields["migraine-medicine-note"], "My middle correction", app)
        save(app, history: true)
        XCTAssertTrue(status(app, history: true).label.contains("changed"))
        let reload = app.buttons["migraine-history-reload"]; reveal(reload, app); reload.tap()
        XCTAssertTrue(status(app, history: true).label.contains("also changed elsewhere"))
        let use = app.buttons["migraine-medicine-use-saved"]; reveal(use, app)
        capture(app, "G014 ambiguous identity keeps both draft and saved medicine versions for review")
        use.tap()
        XCTAssertTrue(status(app, history: true).label.contains("no save was sent"))
        assertDraftCount(4, app)
        save(app, history: true); XCTAssertEqual(status(app, history: true).label, "No migraine detail changes to save.")
    }
}
