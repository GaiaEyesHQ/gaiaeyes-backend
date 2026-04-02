import SwiftUI
#if canImport(UIKit)
import UIKit
#endif

struct HelpCenterView: View {
    let document: HelpCenterDocument
    let context: HelpCenterContext

    @State private var searchText: String = ""

    init(
        document: HelpCenterDocument = HelpCenterContent.shared,
        context: HelpCenterContext = HelpCenterContext()
    ) {
        self.document = document
        self.context = context
    }

    private var launchArticleIDs: [String] {
        [
            "what-gaia-eyes-does",
            "why-sleep-may-not-appear-immediately",
            "how-background-health-sync-works",
            "why-signals-update-at-different-speeds",
            "restore-purchases",
            "free-vs-plus",
            "what-health-data-is-used-for"
        ]
    }

    private var launchArticles: [HelpCenterArticle] {
        launchArticleIDs.compactMap(document.article(id:))
    }

    private var visibleCategories: [HelpCenterCategory] {
        document.categories.filter { !document.articles(in: $0.id).isEmpty }
    }

    private var contactArticles: [HelpCenterArticle] {
        [
            "report-a-bug",
            "need-help-with-billing",
            "health-sync-help",
            "send-feedback"
        ].compactMap(document.article(id:))
    }

    private var searchResults: [HelpCenterArticle] {
        document.search(searchText)
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 18) {
                heroCard

                if searchText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    if !launchArticles.isEmpty {
                        sectionHeader(
                            eyebrow: "Start Here",
                            title: "Launch-critical help",
                            subtitle: "The quickest answers for what Gaia Eyes does, Health sync, freshness, billing, and privacy."
                        )
                        VStack(spacing: 12) {
                            ForEach(launchArticles) { article in
                                NavigationLink {
                                    HelpArticleView(article: article, document: document, context: context)
                                } label: {
                                    HelpArticleCard(article: article, category: document.category(id: article.category))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    sectionHeader(
                        eyebrow: "Browse",
                        title: "Help categories",
                        subtitle: "Everything is grouped by the main questions people usually hit during launch."
                    )
                    VStack(spacing: 12) {
                        ForEach(visibleCategories) { category in
                            NavigationLink {
                                HelpCategoryView(category: category, document: document, context: context)
                            } label: {
                                HelpCategoryCard(category: category, articleCount: document.articles(in: category.id).count)
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    if !contactArticles.isEmpty {
                        sectionHeader(
                            eyebrow: "Contact",
                            title: "Need direct help?",
                            subtitle: "Use the launch-ready contact paths for bugs, billing questions, Health sync issues, or general feedback."
                        )
                        VStack(spacing: 12) {
                            ForEach(contactArticles) { article in
                                NavigationLink {
                                    HelpArticleView(article: article, document: document, context: context)
                                } label: {
                                    HelpArticleCard(article: article, category: document.category(id: article.category))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                } else {
                    sectionHeader(
                        eyebrow: "Search Results",
                        title: searchResults.isEmpty ? "No matching articles" : "\(searchResults.count) matching articles",
                        subtitle: searchResults.isEmpty ? "Try broader keywords like sleep, billing, permissions, or patterns." : "Search checks titles, summaries, keywords, and section text."
                    )
                    VStack(spacing: 12) {
                        ForEach(searchResults) { article in
                            NavigationLink {
                                HelpArticleView(article: article, document: document, context: context)
                            } label: {
                                HelpArticleCard(article: article, category: document.category(id: article.category))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(16)
        }
        .background(Color.black.opacity(0.97).ignoresSafeArea())
        .navigationTitle("Help Center")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $searchText, prompt: "Search help")
    }

    private var heroCard: some View {
        HelpSurfaceCard(accent: Color.teal.opacity(0.7)) {
            VStack(alignment: .leading, spacing: 12) {
                Text("Support and Help")
                    .font(.system(size: 30, weight: .bold, design: .rounded))
                    .foregroundStyle(Color.white)
                Text("Clear answers for Health sync, permissions, billing, privacy, and the basics of how Gaia Eyes works.")
                    .font(.headline)
                    .foregroundStyle(Color.white.opacity(0.86))
                HStack(spacing: 8) {
                    HelpChip(text: "Patterns")
                    HelpChip(text: "Optional Health data")
                    HelpChip(text: "User stays in control")
                }
                Text("Gaia Eyes is built for patterns, not certainties. This center keeps the practical answers close to the product language already in the app.")
                    .font(.subheadline)
                    .foregroundStyle(Color.white.opacity(0.76))
            }
        }
    }

    private func sectionHeader(eyebrow: String, title: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(eyebrow.uppercased())
                .font(.caption2.weight(.semibold))
                .foregroundStyle(Color.white.opacity(0.48))
            Text(title)
                .font(.title3.weight(.bold))
                .foregroundStyle(Color.white)
            Text(subtitle)
                .font(.subheadline)
                .foregroundStyle(Color.white.opacity(0.72))
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

struct HelpCategoryView: View {
    let category: HelpCenterCategory
    let document: HelpCenterDocument
    let context: HelpCenterContext

    private var articles: [HelpCenterArticle] {
        document.articles(in: category.id)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HelpSurfaceCard(accent: Color.teal.opacity(0.6)) {
                    VStack(alignment: .leading, spacing: 10) {
                        Label(category.title, systemImage: category.icon)
                            .font(.title2.weight(.bold))
                            .foregroundStyle(Color.white)
                        Text(category.summary)
                            .font(.subheadline)
                            .foregroundStyle(Color.white.opacity(0.78))
                        Text("\(articles.count) articles")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Color.white.opacity(0.58))
                    }
                }

                VStack(spacing: 12) {
                    ForEach(articles) { article in
                        NavigationLink {
                            HelpArticleView(article: article, document: document, context: context)
                        } label: {
                            HelpArticleCard(article: article, category: category)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(16)
        }
        .background(Color.black.opacity(0.97).ignoresSafeArea())
        .navigationTitle(category.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}

struct HelpArticleView: View {
    let article: HelpCenterArticle
    let document: HelpCenterDocument
    let context: HelpCenterContext

    @Environment(\.openURL) private var openURL

    private var category: HelpCenterCategory? {
        document.category(id: article.category)
    }

    private var healthActionArticleIDs: Set<String> {
        [
            "why-apple-health-is-optional",
            "why-sleep-may-not-appear-immediately",
            "how-background-health-sync-works",
            "wearable-app-not-synced",
            "location-permission-and-local-weather",
            "user-control-over-permissions"
        ]
    }

    private var billingActionArticleIDs: Set<String> {
        [
            "free-vs-plus",
            "restore-purchases",
            "how-subscriptions-work",
            "manage-subscription-on-apple-devices",
            "offer-codes-and-promos",
            "need-help-with-billing"
        ]
    }

    private var understandingArticleIDs: Set<String> {
        [
            "what-gaia-eyes-does",
            "how-gaia-eyes-uses-environmental-signals",
            "how-gaia-eyes-uses-optional-health-data",
            "patterns-not-certainties",
            "scientific-vs-mystical-mode"
        ]
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HelpSurfaceCard(accent: Color.teal.opacity(0.7)) {
                    VStack(alignment: .leading, spacing: 12) {
                        if let category {
                            Text(category.title.uppercased())
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(Color.white.opacity(0.52))
                        }
                        Text(article.title)
                            .font(.system(size: 30, weight: .bold, design: .rounded))
                            .foregroundStyle(Color.white)
                        Text(article.summary)
                            .font(.headline)
                            .foregroundStyle(Color.white.opacity(0.82))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                ForEach(article.bodySections) { section in
                    HelpSurfaceCard(accent: Color.white.opacity(0.08)) {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(section.title)
                                .font(.headline)
                                .foregroundStyle(Color.white)
                            ForEach(section.paragraphs, id: \.self) { paragraph in
                                Text(paragraph)
                                    .font(.subheadline)
                                    .foregroundStyle(Color.white.opacity(0.78))
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            if !section.bullets.isEmpty {
                                VStack(alignment: .leading, spacing: 8) {
                                    ForEach(section.bullets, id: \.self) { bullet in
                                        HStack(alignment: .top, spacing: 10) {
                                            Circle()
                                                .fill(Color.teal.opacity(0.9))
                                                .frame(width: 6, height: 6)
                                                .padding(.top, 7)
                                            Text(bullet)
                                                .font(.subheadline)
                                                .foregroundStyle(Color.white.opacity(0.76))
                                                .fixedSize(horizontal: false, vertical: true)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

        if !article.links.isEmpty || hasSupplementalActions {
                    HelpSurfaceCard(accent: Color.orange.opacity(0.5)) {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Next step")
                                .font(.headline)
                                .foregroundStyle(Color.white)

                            ForEach(article.links) { link in
                                commonAction(link)
                            }

                            supplementalActions
                        }
                    }
                }
            }
            .padding(16)
        }
        .background(Color.black.opacity(0.97).ignoresSafeArea())
        .navigationTitle(article.title)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var hasSupplementalActions: Bool {
        healthActionArticleIDs.contains(article.id) ||
        billingActionArticleIDs.contains(article.id) ||
        understandingArticleIDs.contains(article.id)
    }

    @ViewBuilder
    private func commonAction(_ link: HelpCenterLink) -> some View {
        switch link.kind {
        case .article:
            if let targetArticle = document.article(id: link.target) {
                NavigationLink {
                    HelpArticleView(article: targetArticle, document: document, context: context)
                } label: {
                    HelpActionLabel(title: link.label, systemImage: "arrow.right.circle")
                }
                .buttonStyle(.plain)
            }
        case .category:
            if let targetCategory = document.category(id: link.target) {
                NavigationLink {
                    HelpCategoryView(category: targetCategory, document: document, context: context)
                } label: {
                    HelpActionLabel(title: link.label, systemImage: "square.grid.2x2")
                }
                .buttonStyle(.plain)
            }
        case .url:
            Button {
                if let url = URL(string: link.target) {
                    openURL(url)
                }
            } label: {
                HelpActionLabel(title: link.label, systemImage: "arrow.up.right.square")
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private var supplementalActions: some View {
        if healthActionArticleIDs.contains(article.id) {
            if let appState = context.appState {
                Button {
                    Task { _ = await appState.requestHealthPermissions() }
                } label: {
                    HelpActionLabel(title: "Request / Update Health Permissions", systemImage: "heart.text.square")
                }
                .buttonStyle(.plain)

                Button {
                    Task { _ = await appState.syncHealthBackfillLast30Days() }
                } label: {
                    HelpActionLabel(title: "Sync Last 30 Days", systemImage: "arrow.clockwise")
                }
                .buttonStyle(.plain)
            }

            systemSettingsAction(title: "Open iPhone Settings", systemImage: "gear")
        }

        if billingActionArticleIDs.contains(article.id) {
            NavigationLink {
                SubscribeView(guideProfile: context.guideProfile, helpContext: context)
            } label: {
                HelpActionLabel(title: "Open Account and Membership", systemImage: "creditcard")
            }
            .buttonStyle(.plain)
        }

        if understandingArticleIDs.contains(article.id), let guideProfile = context.guideProfile {
            NavigationLink {
                UnderstandingGaiaEyesView(profile: guideProfile)
            } label: {
                HelpActionLabel(title: "Open the deeper understanding view", systemImage: "globe")
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder
    private func systemSettingsAction(title: String, systemImage: String) -> some View {
#if canImport(UIKit)
        Button {
            guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
            openURL(url)
        } label: {
            HelpActionLabel(title: title, systemImage: systemImage)
        }
        .buttonStyle(.plain)
#endif
    }
}

private struct HelpCategoryCard: View {
    let category: HelpCenterCategory
    let articleCount: Int

    var body: some View {
        HelpSurfaceCard(accent: Color.teal.opacity(0.4)) {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: category.icon)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(Color.teal.opacity(0.95))
                    .frame(width: 28)

                VStack(alignment: .leading, spacing: 6) {
                    Text(category.title)
                        .font(.headline)
                        .foregroundStyle(Color.white)
                    Text(category.summary)
                        .font(.subheadline)
                        .foregroundStyle(Color.white.opacity(0.74))
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 12)

                Text("\(articleCount)")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(Color.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(Color.white.opacity(0.08), in: Capsule())
            }
        }
    }
}

private struct HelpArticleCard: View {
    let article: HelpCenterArticle
    let category: HelpCenterCategory?

    var body: some View {
        HelpSurfaceCard(accent: Color.white.opacity(0.08)) {
            VStack(alignment: .leading, spacing: 8) {
                if let category {
                    Text(category.title.uppercased())
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Color.white.opacity(0.46))
                }
                Text(article.title)
                    .font(.headline)
                    .foregroundStyle(Color.white)
                Text(article.summary)
                    .font(.subheadline)
                    .foregroundStyle(Color.white.opacity(0.74))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

private struct HelpActionLabel: View {
    let title: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: systemImage)
                .foregroundStyle(Color.teal.opacity(0.95))
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Color.white)
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption.weight(.bold))
                .foregroundStyle(Color.white.opacity(0.42))
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }
}

private struct HelpSurfaceCard<Content: View>: View {
    let accent: Color
    let content: Content

    init(accent: Color, @ViewBuilder content: () -> Content) {
        self.accent = accent
        self.content = content()
    }

    var body: some View {
        content
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                LinearGradient(
                    colors: [
                        accent.opacity(0.18),
                        Color.white.opacity(0.06),
                        Color.white.opacity(0.03)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ),
                in: RoundedRectangle(cornerRadius: 22, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
    }
}

private struct HelpChip: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(Color.white)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(Color.white.opacity(0.08), in: Capsule())
    }
}
