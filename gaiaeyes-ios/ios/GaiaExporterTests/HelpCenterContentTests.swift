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
        let data = try Data(contentsOf: contentURL)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        let document = try decoder.decode(HelpCenterDocument.self, from: data)

        #expect(document.categories.count == 7)
        #expect(document.articles.count >= 30)
        #expect(Set(document.articles.map(\.id)).contains("what-gaia-eyes-does"))
        #expect(Set(document.articles.map(\.id)).contains("why-sleep-may-not-appear-immediately"))
        #expect(Set(document.articles.map(\.id)).contains("how-background-health-sync-works"))
        #expect(Set(document.articles.map(\.id)).contains("why-signals-update-at-different-speeds"))
        #expect(Set(document.articles.map(\.id)).contains("restore-purchases"))
        #expect(Set(document.articles.map(\.id)).contains("free-vs-plus"))
        #expect(Set(document.articles.map(\.id)).contains("what-health-data-is-used-for"))
        #expect(Set(document.articles.map(\.id)).contains("no-diagnosis-no-medical-advice"))
        #expect(document.article(id: "scientific-vs-mystical-mode")?.links.isEmpty == true)
        #expect(document.article(id: "what-gaia-eyes-does")?.bodySections.contains(where: { $0.id == "what-it-is-not" && $0.bullets.isEmpty }) == true)
    }
}
