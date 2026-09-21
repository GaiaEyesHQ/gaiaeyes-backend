import Foundation
import Testing
@testable import GaiaEyes

struct HelpCenterContentTests {

    @Test(arguments: [false, true], [false, true])
    func voiceGuideMatchesAvailableEditors(structured: Bool, timeEditing: Bool) throws {
        let iosRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
        let document = try HelpCenterContent.load(from: iosRoot.appendingPathComponent("GaiaExporter/Resources/HelpCenterContent.json"))
        let article = try #require(document.article(id: "voice-commands"))
        let sections = article.displaySections(structuredMigraine: structured, timeEditing: timeEditing)
        let ids = Set(sections.map(\.id))
        #expect(ids.contains("voice-review-basic") == !structured)
        #expect(ids.contains("voice-review-structured") == structured)
        #expect(ids.contains("voice-review-times") == timeEditing)
        #expect(ids.contains("voice-start") && ids.contains("voice-stop"))
        #expect(ids.contains("voice-offline") && ids.contains("voice-dictation"))
        #expect(document.search("Siri migraine").contains(where: { $0.id == article.id }))
        let other = try #require(document.article(id: "what-gaia-eyes-does"))
        #expect(other.displaySections(structuredMigraine: structured, timeEditing: timeEditing) == other.bodySections)
    }

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
