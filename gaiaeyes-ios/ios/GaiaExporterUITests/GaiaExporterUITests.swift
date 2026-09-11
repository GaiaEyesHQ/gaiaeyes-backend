//
//  GaiaExporterUITests.swift
//  GaiaExporterUITests
//
//  Created by Jennifer O'Brien on 8/24/25.
//

import XCTest

final class GaiaExporterUITests: XCTestCase {

    override func setUpWithError() throws {
        // Put setup code here. This method is called before the invocation of each test method in the class.

        // In UI tests it is usually best to stop immediately when a failure occurs.
        continueAfterFailure = false

        // In UI tests it’s important to set the initial state - such as interface orientation - required for your tests before they run. The setUp method is a good place to do this.
    }

    override func tearDownWithError() throws {
        // Put teardown code here. This method is called after the invocation of each test method in the class.
    }

    @MainActor
    func testExample() throws {
        // UI tests must launch the application that they test.
        let app = XCUIApplication()
        app.launch()

        // Use XCTAssert and related functions to verify your tests produce the correct results.
    }

    @MainActor
    private func launchMigraine(_ scenario: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-gaia-preview-migraine-follow-up-fixture",
            "-gaia-enable-structured-migraine-follow-up", "-gaia-migraine-scenario", scenario]
        app.launch()
        return app
    }

    @MainActor
    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<8 {
            if element.exists && element.isHittable { return }
            // Keep the gesture above the keyboard on smaller phone layouts.
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45))
                .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.18)))
        }
        XCTAssertTrue(element.isHittable)
    }

    @MainActor
    private func clearMedicines(in app: XCUIApplication) {
        let picker = app.buttons["migraine-medicine-clear"]
        reveal(picker, in: app)
        picker.tap()
        app.buttons.matching(identifier: "Clear all entries").allElementsBoundByIndex.last!.tap()
    }

    @MainActor
    private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    @MainActor
    func testMigraineActualSheetUncertainSaveAndIdenticalRetry() throws {
        let app = launchMigraine("committed-timeout")
        XCTAssertTrue(app.textFields["Early signs, separated by commas"].waitForExistence(timeout: 8))
        XCTAssertTrue(app.buttons["Later the same day"].exists)
        app.buttons["Later the same day"].tap()
        capture(app, name: "Actual follow-up options and loaded migraine details")
        clearMedicines(in: app)
        let note = app.textViews["migraine-episode-note"]
        reveal(note, in: app)
        note.tap()
        note.typeText(" Retain this answer on failure.")
        let save = app.buttons["migraine-save-response"]
        reveal(save, in: app)
        save.tap()
        let error = app.staticTexts["migraine-save-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 8))
        XCTAssertTrue(error.label.contains("could not be confirmed"))
        XCTAssertFalse(app.staticTexts["migraine-confirmed"].exists)
        XCTAssertTrue((note.value as? String ?? "").contains("Retain this answer on failure."))
        reveal(error, in: app)
        XCTAssertFalse(app.keyboards.firstMatch.exists)
        capture(app, name: "Actual form retains answers after uncertain save")
        reveal(save, in: app)
        save.tap()
        XCTAssertTrue(app.staticTexts["migraine-confirmed"].waitForExistence(timeout: 8))
    }

    @MainActor
    func testMigraineActualSheetConflictRetainsAnswers() throws {
        let app = launchMigraine("conflict")
        XCTAssertTrue(app.textFields["Early signs, separated by commas"].waitForExistence(timeout: 8))
        clearMedicines(in: app)
        let save = app.buttons["migraine-save-response"]
        reveal(save, in: app)
        save.tap()
        XCTAssertTrue(app.staticTexts["migraine-save-error"].waitForExistence(timeout: 8))
        XCTAssertFalse(app.staticTexts["migraine-confirmed"].exists)
        XCTAssertTrue(app.textViews["migraine-episode-note"].exists)
        reveal(app.staticTexts["migraine-save-error"], in: app)
        capture(app, name: "Actual conflict retains draft and save control")
    }

    @MainActor
    func testMigraineActualSheetUnsupportedCapabilityFallback() throws {
        let app = launchMigraine("unsupported")
        let message = app.staticTexts["This server does not support extra migraine details yet. You can still save this check-in."]
        XCTAssertTrue(message.waitForExistence(timeout: 8))
        XCTAssertFalse(app.textFields["Medicine name"].exists)
        let save = app.buttons["migraine-save-response"]
        reveal(save, in: app)
        save.tap()
        XCTAssertTrue(app.staticTexts["migraine-confirmed"].waitForExistence(timeout: 8))
    }

    @MainActor
    func testMigraineActualSheetLoadFailureCannotSilentlyFallback() throws {
        let app = launchMigraine("load-failure")
        XCTAssertTrue(app.buttons["Retry loading migraine details"].waitForExistence(timeout: 8))
        let save = app.buttons["migraine-save-response"]
        reveal(save, in: app)
        XCTAssertFalse(save.isEnabled)
        XCTAssertFalse(app.staticTexts["migraine-confirmed"].exists)
    }

    @MainActor
    func testMigraineActualSheetAccountChangeRetainsDraftWithoutSaving() throws {
        let app = launchMigraine("account-change")
        XCTAssertTrue(app.textFields["Early signs, separated by commas"].waitForExistence(timeout: 8))
        app.buttons["Switch synthetic account"].tap()
        clearMedicines(in: app)
        let save = app.buttons["migraine-save-response"]
        reveal(save, in: app)
        save.tap()
        let error = app.staticTexts["migraine-save-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 8))
        XCTAssertTrue(error.label.contains("account changed"))
        XCTAssertFalse(app.staticTexts["migraine-confirmed"].exists)
    }

    @MainActor
    func testMigraineActualHistoricalEditorSavesEditedNote() throws {
        let app = launchMigraine("history")
        let note = app.textFields["migraine-history-note"]
        XCTAssertTrue(note.waitForExistence(timeout: 8))
        note.tap()
        note.typeText(" Updated through the actual history editor.")
        let save = app.buttons["migraine-history-save"]
        reveal(save, in: app)
        save.tap()
        let status = app.staticTexts["migraine-history-status"]
        XCTAssertTrue(status.waitForExistence(timeout: 8))
        XCTAssertEqual(status.label, "Migraine details saved.")
        capture(app, name: "Actual historical editor confirms saved details")
    }

    @MainActor
    private func revealAbove(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<8 {
            if element.exists && element.isHittable { return }
            app.swipeDown()
        }
        XCTAssertTrue(element.isHittable)
    }

    @MainActor
    private func checkInFlightInputs(history: Bool, legacy: Bool, outcome: String) throws {
        let lane = history ? (legacy ? "history-legacy" : "history") : (legacy ? "legacy-follow-up" : "follow-up")
        let app = launchMigraine("delayed-\(lane)-\(outcome)")
        let note = history ? app.textFields["migraine-history-note"] : app.textViews["migraine-episode-note"]
        XCTAssertTrue(note.waitForExistence(timeout: 8))
        if history || !legacy {
            XCTAssertTrue(app.textFields["Early signs, separated by commas"].waitForExistence(timeout: 8))
        }
        if !history { reveal(note, in: app) }
        note.tap()
        note.typeText(" G-R19 submitted answer.")
        let submitted = (note.value as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let saveID = history ? (legacy ? "migraine-history-legacy-save" : "migraine-history-save") : "migraine-save-response"
        let save = app.buttons[saveID]
        reveal(save, in: app)
        save.tap()
        XCTAssertTrue(save.label.contains("Saving"))
        XCTAssertFalse(save.isEnabled)
        if history {
            XCTAssertFalse(app.buttons["migraine-history-save"].isEnabled)
            XCTAssertFalse(app.buttons["migraine-history-legacy-save"].isEnabled)
        }
        if history || !legacy {
            XCTAssertFalse(app.buttons["migraine-medicine-choice"].isEnabled)
            XCTAssertFalse(app.textFields["Early signs, separated by commas"].isEnabled)
            XCTAssertFalse(app.textFields["Medicine name"].isEnabled)
            XCTAssertFalse(app.textFields["Dose"].isEnabled)
            XCTAssertFalse(app.textFields["Unit (mg, mL…)"].isEnabled)
        }
        if history { revealAbove(note, in: app) }
        XCTAssertFalse(note.isEnabled)
        // A real attempted tap cannot focus a disabled input or open its keyboard.
        note.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
        XCTAssertFalse(app.keyboards.firstMatch.exists)
        XCTAssertEqual((note.value as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines), submitted)
        if history {
            let severity = app.steppers["migraine-history-severity"]
            revealAbove(severity, in: app)
            XCTAssertEqual(app.staticTexts["migraine-fixture-save-state"].label, "Save pending")
            let severityBefore = severity.label
            let controls = severity.buttons.allElementsBoundByIndex
            XCTAssertEqual(controls.count, 2, severity.debugDescription)
            for control in controls {
                // Scroll-recreated controls must remain locked until acknowledgement.
                control.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()
                XCTAssertEqual(severity.label, severityBefore)
                XCTAssertEqual(app.staticTexts["migraine-fixture-save-state"].label, "Save pending")
            }
        } else {
            let option = app.buttons["Later the same day"]
            revealAbove(option, in: app)
            XCTAssertFalse(option.isEnabled)
        }
        if outcome == "success" { capture(app, name: "G-R19 \(lane) inputs locked before acknowledgement") }
        app.buttons["migraine-release-response"].tap()
        let receipt = app.staticTexts["migraine-submitted-note"]
        XCTAssertTrue(receipt.waitForExistence(timeout: 8))
        XCTAssertEqual(receipt.label, submitted)
        if !history && outcome == "success" {
            XCTAssertTrue(app.staticTexts["migraine-confirmed"].waitForExistence(timeout: 8))
        } else {
            let statusID = history ? (legacy ? "migraine-history-legacy-status" : "migraine-history-status") : "migraine-save-error"
            let status = app.staticTexts[statusID]
            reveal(status, in: app)
            XCTAssertTrue(status.waitForExistence(timeout: 8))
            if outcome == "success" {
                XCTAssertTrue(status.label.contains("saved"))
            } else {
                XCTAssertFalse(app.staticTexts["migraine-confirmed"].exists)
                XCTAssertFalse(status.label == "Changes saved." || status.label == "Migraine details saved.")
            }
            revealAbove(note, in: app)
            XCTAssertTrue(note.isEnabled)
            XCTAssertEqual((note.value as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines), submitted)
            if history {
                let severity = app.steppers["migraine-history-severity"]
                revealAbove(severity, in: app)
                let severityBefore = severity.label
                severity.buttons.element(boundBy: 0).tap()
                XCTAssertNotEqual(severity.label, severityBefore)
            }
            note.tap()
            note.typeText(" Editable again.")
            XCTAssertTrue((note.value as? String ?? "").contains("Editable again."))
        }
    }

    @MainActor
    func testGR19FollowUpStructuredSuccess() throws {
        try checkInFlightInputs(history: false, legacy: false, outcome: "success")
    }

    @MainActor
    func testGR19FollowUpStructuredConflict() throws {
        try checkInFlightInputs(history: false, legacy: false, outcome: "conflict")
    }

    @MainActor
    func testGR19FollowUpStructuredCancelled() throws {
        try checkInFlightInputs(history: false, legacy: false, outcome: "cancelled")
    }

    @MainActor
    func testGR19FollowUpLegacySuccess() throws {
        try checkInFlightInputs(history: false, legacy: true, outcome: "success")
    }

    @MainActor
    func testGR19FollowUpLegacyConflict() throws {
        try checkInFlightInputs(history: false, legacy: true, outcome: "conflict")
    }

    @MainActor
    func testGR19FollowUpLegacyCancelled() throws {
        try checkInFlightInputs(history: false, legacy: true, outcome: "cancelled")
    }

    @MainActor
    func testGR19HistoryStructuredSuccess() throws {
        try checkInFlightInputs(history: true, legacy: false, outcome: "success")
    }

    @MainActor
    func testGR19HistoryStructuredConflict() throws {
        try checkInFlightInputs(history: true, legacy: false, outcome: "conflict")
    }

    @MainActor
    func testGR19HistoryStructuredCancelled() throws {
        try checkInFlightInputs(history: true, legacy: false, outcome: "cancelled")
    }

    @MainActor
    func testGR19HistoryLegacySuccess() throws {
        try checkInFlightInputs(history: true, legacy: true, outcome: "success")
    }

    @MainActor
    func testGR19HistoryLegacyConflict() throws {
        try checkInFlightInputs(history: true, legacy: true, outcome: "conflict")
    }

    @MainActor
    func testGR19HistoryLegacyCancelled() throws {
        try checkInFlightInputs(history: true, legacy: true, outcome: "cancelled")
    }

    @MainActor
    func testLaunchPerformance() throws {
        // This measures how long it takes to launch your application.
        measure(metrics: [XCTApplicationLaunchMetric()]) {
            XCUIApplication().launch()
        }
    }
}
