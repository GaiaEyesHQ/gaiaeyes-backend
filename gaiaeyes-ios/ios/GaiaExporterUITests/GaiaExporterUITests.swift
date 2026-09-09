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
    func testMigraineFollowUpFixtureIsReadable() throws {
        let app = XCUIApplication()
        app.launchArguments = ["-gaia-preview-migraine-follow-up-fixture"]
        app.launch()

        XCTAssertTrue(app.staticTexts["How is your migraine now?"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Migraine details"].exists)
        XCTAssertTrue(app.textFields["Early signs, separated by commas"].exists)
        XCTAssertTrue(app.textFields["Medicine name"].exists)
        XCTAssertTrue(app.buttons["Save response"].exists)

        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "Migraine follow-up fixture"
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    @MainActor
    func testLaunchPerformance() throws {
        // This measures how long it takes to launch your application.
        measure(metrics: [XCTApplicationLaunchMetric()]) {
            XCUIApplication().launch()
        }
    }
}
