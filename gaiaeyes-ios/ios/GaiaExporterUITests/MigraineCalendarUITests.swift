import XCTest

final class MigraineCalendarUITests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }

    @MainActor
    private func launch(_ scenario: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-gaia-preview-migraine-follow-up-fixture", "-gaia-enable-migraine-calendar",
            "-gaia-enable-structured-migraine-follow-up", "-gaia-migraine-scenario", scenario]
        app.launch(); return app
    }
    @MainActor
    private func reveal(_ element: XCUIElement, app: XCUIApplication) {
        for _ in 0..<10 {
            if element.exists && element.isHittable { return }
            // Begin above the software keyboard on smaller phones.
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.18)))
        }
        XCTAssertTrue(element.isHittable)
    }
    @MainActor
    private func screenshot(_ app: XCUIApplication, name: String) {
        let item = XCTAttachment(screenshot: app.screenshot()); item.name = name; item.lifetime = .keepAlways; add(item)
    }

    @MainActor
    func testCalendarSelectionEditorIdentityAndRefreshAfterSave() throws {
        let app = launch("calendar-success")
        XCTAssertTrue(app.staticTexts["migraine-calendar-count"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["migraine-calendar-count"].label, "2 migraine episodes")
        XCTAssertTrue(app.staticTexts["migraine-calendar-asof"].exists)
        screenshot(app, name: "G012 month and selected-day episodes")
        let second = app.buttons["migraine-calendar-episode-33333333-3333-4333-8333-333333333333"]
        reveal(second, app: app); second.tap()
        let note = app.textFields["migraine-history-note"]
        XCTAssertTrue(note.waitForExistence(timeout: 8))
        XCTAssertEqual(note.value as? String, "Synthetic episode 2")
        note.tap(); note.typeText(" edited in calendar")
        let save = app.buttons["migraine-history-legacy-save"]
        reveal(save, app: app); save.tap()
        let status = app.staticTexts["migraine-history-legacy-status"]
        reveal(status, app: app)
        XCTAssertEqual(status.label, "Changes saved.")
        app.buttons["migraine-calendar-editor-done"].tap()
        let returned = app.buttons["migraine-calendar-episode-33333333-3333-4333-8333-333333333333"]
        reveal(returned, app: app)
        XCTAssertTrue(returned.label.contains("edited in calendar"))
        XCTAssertTrue(app.buttons["migraine-calendar-episode-11111111-1111-4111-8111-111111111111"].exists)
        app.swipeDown(); app.swipeDown()
        app.buttons["migraine-calendar-day-2026-09-08"].tap()
        XCTAssertEqual(app.staticTexts["migraine-calendar-count"].label, "1 migraine episode")
        app.buttons["migraine-calendar-next"].tap()
        XCTAssertTrue(app.staticTexts["No migraine episodes recorded for this day."].waitForExistence(timeout: 8))
        app.buttons["migraine-calendar-previous"].tap()
        app.buttons["migraine-calendar-day-2026-09-09"].tap()
        XCTAssertTrue(app.staticTexts["2 migraine episodes"].waitForExistence(timeout: 8))
    }

    @MainActor
    func testCalendarPartialPaginationRetry() throws {
        let app = launch("calendar-pagination")
        XCTAssertTrue(app.staticTexts["migraine-calendar-error"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["migraine-calendar-incomplete"].exists)
        XCTAssertFalse(app.staticTexts["migraine-calendar-count"].exists)
        screenshot(app, name: "G012 incomplete page and retry")
        app.buttons["migraine-calendar-retry"].tap()
        XCTAssertTrue(app.staticTexts["2 migraine episodes"].waitForExistence(timeout: 10))
    }

    @MainActor
    func testCalendarEntryPreservesOtherSymptomHistory() throws {
        let app = launch("calendar-entry")
        XCTAssertTrue(app.staticTexts["Fatigue"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["migraine-calendar-open"].exists)
        screenshot(app, name: "G012 calendar alongside other symptom history")
        app.buttons["migraine-calendar-open"].tap()
        XCTAssertTrue(app.staticTexts["migraine-calendar-month"].waitForExistence(timeout: 10))
    }

    @MainActor
    func testCalendarEditorCannotCloseDuringSave() throws {
        let app = launch("calendar-save-pending")
        XCTAssertTrue(app.staticTexts["migraine-calendar-count"].waitForExistence(timeout: 10))
        let episode = app.buttons["migraine-calendar-episode-33333333-3333-4333-8333-333333333333"]
        reveal(episode, app: app); episode.tap()
        let note = app.textFields["migraine-history-note"]
        XCTAssertTrue(note.waitForExistence(timeout: 8))
        note.tap(); note.typeText(" saved from calendar")
        let save = app.buttons["migraine-history-legacy-save"]
        reveal(save, app: app); save.tap()
        XCTAssertFalse(app.buttons["migraine-calendar-editor-done"].isEnabled)
        XCTAssertFalse(save.isEnabled)
        app.buttons["migraine-calendar-release-save"].tap()
        let status = app.staticTexts["migraine-history-legacy-status"]
        reveal(status, app: app)
        XCTAssertEqual(status.label, "Changes saved.")
        XCTAssertTrue(app.buttons["migraine-calendar-editor-done"].isEnabled)
        app.buttons["migraine-calendar-editor-done"].tap()
        reveal(episode, app: app)
        XCTAssertTrue(episode.label.contains("saved from calendar"))
    }

    @MainActor
    func testCalendarErrorAndEmptyAreDistinct() throws {
        let app = launch("calendar-error")
        XCTAssertTrue(app.staticTexts["migraine-calendar-error"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["migraine-calendar-count"].exists)
        app.buttons["migraine-calendar-retry"].tap()
        XCTAssertTrue(app.staticTexts["2 migraine episodes"].waitForExistence(timeout: 10))
        app.terminate()
        let empty = launch("calendar-empty")
        XCTAssertTrue(empty.staticTexts["No migraine episodes recorded for this day."].waitForExistence(timeout: 10))
        screenshot(empty, name: "G012 complete empty month")
    }

    @MainActor
    func testCalendarConflictRefreshesFromFirstPage() throws {
        let app = launch("calendar-conflict")
        XCTAssertTrue(app.staticTexts["migraine-calendar-error"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["migraine-calendar-error"].label.contains("History changed"))
        XCTAssertFalse(app.buttons["migraine-calendar-episode-11111111-1111-4111-8111-111111111111"].exists)
        app.buttons["migraine-calendar-refresh"].tap()
        XCTAssertTrue(app.staticTexts["2 migraine episodes"].waitForExistence(timeout: 10))
    }

    @MainActor
    func testCalendarMissingCapabilityIsNotEmptyHistory() throws {
        let app = launch("calendar-unsupported")
        XCTAssertTrue(app.staticTexts["migraine-calendar-error"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["migraine-calendar-error"].label.contains("not available"))
        XCTAssertFalse(app.staticTexts["migraine-calendar-count"].exists)
    }

    @MainActor
    func testCalendarMonthChangeWhileResponsePending() throws {
        let app = launch("calendar-pending-month")
        XCTAssertTrue(app.activityIndicators["migraine-calendar-loading"].waitForExistence(timeout: 8))
        app.buttons["migraine-calendar-next"].tap()
        XCTAssertTrue(app.staticTexts["No migraine episodes recorded for this day."].waitForExistence(timeout: 10))
        app.buttons["migraine-release-response"].tap()
        XCTAssertEqual(app.staticTexts["migraine-calendar-month"].label, "October 2026")
        XCTAssertEqual(app.staticTexts["migraine-calendar-count"].label, "No migraine episodes recorded for this day.")
        screenshot(app, name: "G012 changed month ignores earlier pending reply")
    }

    @MainActor
    func testCalendarAccountChangeWhileResponsePending() throws {
        let app = launch("calendar-pending-account")
        XCTAssertTrue(app.activityIndicators["migraine-calendar-loading"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.buttons["Switch synthetic account"].waitForExistence(timeout: 8))
        app.buttons["Switch synthetic account"].tap()
        XCTAssertTrue(app.staticTexts["No migraine episodes recorded for this day."].waitForExistence(timeout: 10))
        app.buttons["migraine-release-response"].tap()
        XCTAssertFalse(app.buttons["migraine-calendar-episode-11111111-1111-4111-8111-111111111111"].exists)
    }
}
