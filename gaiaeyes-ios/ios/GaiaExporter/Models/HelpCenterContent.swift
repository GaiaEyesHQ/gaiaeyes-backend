import Foundation

struct HelpCenterMetadata: Decodable, Hashable {
    let updatedAt: String
    let supportEmail: String
    let webSupportURL: String

    private enum CodingKeys: String, CodingKey {
        case updatedAt
        case supportEmail
        case webSupportURL = "webSupportUrl"
    }
}

struct HelpCenterCategory: Identifiable, Decodable, Hashable {
    let id: String
    let title: String
    let summary: String
    let icon: String
}

struct HelpCenterLink: Identifiable, Decodable, Hashable {
    enum Kind: String, Decodable {
        case article
        case category
        case url
    }

    let id: String
    let label: String
    let kind: Kind
    let target: String
}

struct HelpCenterSection: Identifiable, Decodable, Hashable {
    let id: String
    let title: String
    let paragraphs: [String]
    let bullets: [String]

    private enum CodingKeys: String, CodingKey {
        case id
        case title
        case paragraphs
        case bullets
    }

    init(id: String, title: String, paragraphs: [String], bullets: [String] = []) {
        self.id = id
        self.title = title
        self.paragraphs = paragraphs
        self.bullets = bullets
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        paragraphs = try container.decodeIfPresent([String].self, forKey: .paragraphs) ?? []
        bullets = try container.decodeIfPresent([String].self, forKey: .bullets) ?? []
    }
}

struct HelpCenterArticle: Identifiable, Decodable, Hashable {
    let id: String
    let title: String
    let summary: String
    let category: String
    let keywords: [String]
    let bodySections: [HelpCenterSection]
    let links: [HelpCenterLink]

    private enum CodingKeys: String, CodingKey {
        case id
        case title
        case summary
        case category
        case keywords
        case bodySections
        case links
    }

    init(
        id: String,
        title: String,
        summary: String,
        category: String,
        keywords: [String] = [],
        bodySections: [HelpCenterSection] = [],
        links: [HelpCenterLink] = []
    ) {
        self.id = id
        self.title = title
        self.summary = summary
        self.category = category
        self.keywords = keywords
        self.bodySections = bodySections
        self.links = links
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        summary = try container.decode(String.self, forKey: .summary)
        category = try container.decode(String.self, forKey: .category)
        keywords = try container.decodeIfPresent([String].self, forKey: .keywords) ?? []
        bodySections = try container.decodeIfPresent([HelpCenterSection].self, forKey: .bodySections) ?? []
        links = try container.decodeIfPresent([HelpCenterLink].self, forKey: .links) ?? []
    }

    var searchText: String {
        let sectionText = bodySections.flatMap { $0.paragraphs + $0.bullets + [$0.title] }
        return ([title, summary] + keywords + sectionText).joined(separator: " ").lowercased()
    }
}

struct HelpCenterDocument: Decodable, Hashable {
    let metadata: HelpCenterMetadata
    let categories: [HelpCenterCategory]
    let articles: [HelpCenterArticle]

    func category(id: String) -> HelpCenterCategory? {
        categories.first(where: { $0.id == id })
    }

    func article(id: String) -> HelpCenterArticle? {
        articles.first(where: { $0.id == id })
    }

    func articles(in categoryID: String) -> [HelpCenterArticle] {
        articles.filter { $0.category == categoryID }
    }

    func search(_ query: String) -> [HelpCenterArticle] {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !trimmed.isEmpty else { return [] }

        let terms = trimmed.split(whereSeparator: \.isWhitespace).map(String.init)
        return articles
            .filter { article in
                terms.allSatisfy { article.searchText.contains($0) }
            }
            .sorted { lhs, rhs in
                score(for: lhs, query: trimmed) > score(for: rhs, query: trimmed)
            }
    }

    private func score(for article: HelpCenterArticle, query: String) -> Int {
        let title = article.title.lowercased()
        let summary = article.summary.lowercased()
        if title == query { return 100 }
        if title.hasPrefix(query) { return 80 }
        if title.contains(query) { return 60 }
        if summary.contains(query) { return 40 }
        return 20
    }
}

struct HelpCenterContext {
    var guideProfile: GuideProfile? = nil
    var appState: AppState? = nil
}

enum HelpCenterContent {
    static let shared: HelpCenterDocument = {
        do {
            return try load()
        } catch {
            print("Failed to load HelpCenterContent.json: \(error)")
            return HelpCenterDocument(metadata: HelpCenterMetadata(updatedAt: "", supportEmail: "", webSupportURL: ""), categories: [], articles: [])
        }
    }()

    static func load(bundle: Bundle = .main) throws -> HelpCenterDocument {
        guard let url = bundle.url(forResource: "HelpCenterContent", withExtension: "json") else {
            throw CocoaError(.fileNoSuchFile)
        }
        return try load(from: url)
    }

    static func load(from url: URL) throws -> HelpCenterDocument {
        let data = try Data(contentsOf: url)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(HelpCenterDocument.self, from: data)
    }
}
