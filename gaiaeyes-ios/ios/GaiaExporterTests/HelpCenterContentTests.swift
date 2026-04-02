import Foundation
import Testing
@testable import GaiaEyes

struct HelpCenterContentTests {

    @Test
    func decodesSharedHelpCenterContent() throws {
        let iosRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let contentURL = iosRoot.appendingPathComponent("GaiaExporter/Resources/HelpCenterContent.json")

        let document = try HelpCenterContent.load(from: contentURL)

        #expect(document.categories.count == 7)
        #expect(document.articles.count >= 30)
        #expect(document.article(id: "what-gaia-eyes-does") != nil)
        #expect(document.article(id: "why-sleep-may-not-appear-immediately") != nil)
        #expect(document.article(id: "how-background-health-sync-works") != nil)
        #expect(document.article(id: "why-signals-update-at-different-speeds") != nil)
        #expect(document.article(id: "restore-purchases") != nil)
        #expect(document.article(id: "free-vs-plus") != nil)
        #expect(document.article(id: "what-health-data-is-used-for") != nil)
        #expect(document.article(id: "no-diagnosis-no-medical-advice") != nil)
    }
}
