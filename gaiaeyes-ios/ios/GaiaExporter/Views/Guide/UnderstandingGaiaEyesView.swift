import SwiftUI

struct UnderstandingGaiaEyesView: View {
    let profile: GuideProfile

    private var content: UnderstandingPageContent {
        UnderstandingGaiaEyesContent.page(mode: profile.mode, tone: profile.tone)
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 18) {
                UnderstandingIntroCard(
                    profile: profile,
                    title: content.title,
                    subtitle: content.subtitle,
                    introLines: content.introLines
                )

                DataSourcesSection(
                    guideType: profile.guideType,
                    categories: content.dataCategories
                )

                HowItWorksSection(
                    guideType: profile.guideType,
                    steps: content.howItWorksSteps
                )

                WhatItDoesNotDoSection(
                    guideType: profile.guideType,
                    limitations: content.limitations
                )

                UnderstandingSectionCard(
                    guideType: profile.guideType,
                    emphasis: .standard,
                    eyebrow: "Research Context",
                    title: "What the research says",
                    subtitle: "These topic summaries are intentionally short and careful. They give context for why Gaia watches certain signals without turning them into proof."
                ) {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(content.researchTopics) { topic in
                            ResearchTopicCard(
                                guideType: profile.guideType,
                                topic: topic
                            )
                        }
                    }
                }

                SourceLinksSection(
                    guideType: profile.guideType,
                    sourceGroups: content.sourceGroups
                )

                if let futureNote = content.futureNote, !futureNote.isEmpty {
                    UnderstandingSectionCard(
                        guideType: profile.guideType,
                        emphasis: .quiet,
                        eyebrow: "Looking Ahead",
                        title: "A small note on future community context",
                        subtitle: futureNote
                    ) {
                        EmptyView()
                    }
                }
            }
            .padding(16)
        }
        .background(Color.black.opacity(0.97).ignoresSafeArea())
        .navigationTitle(content.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct UnderstandingIntroCard: View {
    let profile: GuideProfile
    let title: String
    let subtitle: String
    let introLines: [String]

    private var style: GuidePromptStyle {
        GuidePromptStyle.style(for: profile.guideType, emphasis: .elevated)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .center, spacing: 16) {
                GuideAvatarView(
                    guide: profile.guideType,
                    expression: .helpful,
                    size: .large,
                    emphasis: .elevated,
                    showBackingPlate: true,
                    animate: true
                )

                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.system(size: 30, weight: .bold, design: .rounded))
                        .foregroundStyle(style.primaryText)
                    Text(subtitle)
                        .font(.headline)
                        .foregroundStyle(style.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("\(profile.mode.title) mode / \(profile.tone.title) tone")
                        .font(.caption)
                        .foregroundStyle(style.tertiaryText)
                }
            }

            HStack(spacing: 8) {
                introChip("Signals")
                introChip("Patterns")
                introChip("Limits")
            }

            VStack(alignment: .leading, spacing: 10) {
                ForEach(introLines, id: \.self) { line in
                    Text(line)
                        .font(.subheadline)
                        .foregroundStyle(style.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            LinearGradient(
                colors: [
                    style.accent.opacity(0.22),
                    Color.white.opacity(0.07),
                    Color.white.opacity(0.04)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            ),
            in: RoundedRectangle(cornerRadius: 26, style: .continuous)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .stroke(style.cardBorder, lineWidth: 1)
        )
        .shadow(color: style.glow, radius: 18)
    }

    private func introChip(_ text: String) -> some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .foregroundStyle(style.primaryText)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(style.accent.opacity(0.18), in: Capsule())
    }
}

private struct DataSourcesSection: View {
    let guideType: GuideType
    let categories: [UnderstandingCategory]

    var body: some View {
        UnderstandingSectionCard(
            guideType: guideType,
            emphasis: .standard,
            eyebrow: "What Gaia Uses",
            title: "What data Gaia Eyes uses",
            subtitle: "The app combines outside conditions, body context, and your own feedback. It stays explicit about categories without dumping every low-level field name into the page."
        ) {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(categories) { category in
                    UnderstandingDataCategoryCard(
                        guideType: guideType,
                        category: category
                    )
                }
            }
        }
    }
}

private struct HowItWorksSection: View {
    let guideType: GuideType
    let steps: [String]

    var body: some View {
        UnderstandingSectionCard(
            guideType: guideType,
            emphasis: .standard,
            eyebrow: "Pattern Loop",
            title: "How Gaia Eyes turns data into insights",
            subtitle: "The loop is intentionally simple: watch signals, compare them with how you feel, and make the useful patterns easier to notice over time."
        ) {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(Array(steps.enumerated()), id: \.offset) { index, step in
                    UnderstandingStepRow(
                        guideType: guideType,
                        index: index + 1,
                        text: step
                    )
                }
            }
        }
    }
}

private struct WhatItDoesNotDoSection: View {
    let guideType: GuideType
    let limitations: [String]

    var body: some View {
        UnderstandingSectionCard(
            guideType: guideType,
            emphasis: .quiet,
            eyebrow: "Limits",
            title: "What Gaia Eyes does not do",
            subtitle: "This is an observational tool. It is meant to support pattern-finding, not replace clinical judgment or turn weak evidence into certainty."
        ) {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(limitations, id: \.self) { limitation in
                    UnderstandingBulletRow(
                        guideType: guideType,
                        systemImage: "shield.lefthalf.filled",
                        text: limitation
                    )
                }
            }
        }
    }
}

private struct ResearchTopicCard: View {
    let guideType: GuideType
    let topic: UnderstandingTopic

    private var style: GuidePromptStyle {
        GuidePromptStyle.style(for: guideType, emphasis: .quiet)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(topic.title)
                        .font(.headline)
                        .foregroundStyle(style.primaryText)
                    if let evidenceLabel = topic.evidenceLabel, !evidenceLabel.isEmpty {
                        Text(evidenceLabel)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(style.primaryText)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(style.accent.opacity(0.16), in: Capsule())
                    }
                }
                Spacer(minLength: 0)
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(topic.summaryLines, id: \.self) { line in
                    Text(line)
                        .font(.subheadline)
                        .foregroundStyle(style.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if !topic.sourceLinks.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(topic.sourceLinks.prefix(2)) { source in
                        UnderstandingSourceLinkRow(
                            guideType: guideType,
                            source: source
                        )
                    }
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.035), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(style.cardBorder.opacity(0.6), lineWidth: 1)
        )
    }
}

private struct SourceLinksSection: View {
    let guideType: GuideType
    let sourceGroups: [UnderstandingSourceGroup]

    var body: some View {
        UnderstandingSectionCard(
            guideType: guideType,
            emphasis: .quiet,
            eyebrow: "Learn More",
            title: "Sources and learn more",
            subtitle: "Operational data providers and the research context used on this page are grouped here so the page stays readable."
        ) {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(sourceGroups) { group in
                    UnderstandingSourceGroupCard(
                        guideType: guideType,
                        group: group
                    )
                }
            }
        }
    }
}

private struct UnderstandingSectionCard<Content: View>: View {
    let guideType: GuideType
    let emphasis: GuideAvatarEmphasis
    let eyebrow: String
    let title: String
    let subtitle: String
    let content: Content

    init(
        guideType: GuideType,
        emphasis: GuideAvatarEmphasis,
        eyebrow: String,
        title: String,
        subtitle: String,
        @ViewBuilder content: () -> Content
    ) {
        self.guideType = guideType
        self.emphasis = emphasis
        self.eyebrow = eyebrow
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        let style = GuidePromptStyle.style(for: guideType, emphasis: emphasis)

        VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 6) {
                Text(eyebrow.uppercased())
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(style.tertiaryText)
                Text(title)
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(style.primaryText)
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(style.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }

            content
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(style.cardFill, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(style.cardBorder, lineWidth: 1)
        )
        .shadow(color: style.glow, radius: emphasis == .quiet ? 10 : 14)
    }
}

private struct UnderstandingDataCategoryCard: View {
    let guideType: GuideType
    let category: UnderstandingCategory

    private static let columns = [
        GridItem(.adaptive(minimum: 132, maximum: 220), spacing: 8, alignment: .topLeading)
    ]

    private var style: GuidePromptStyle {
        GuidePromptStyle.style(for: guideType, emphasis: .quiet)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(category.title)
                .font(.headline)
                .foregroundStyle(style.primaryText)
            Text(category.summary)
                .font(.subheadline)
                .foregroundStyle(style.secondaryText)
                .fixedSize(horizontal: false, vertical: true)

            LazyVGrid(columns: Self.columns, alignment: .leading, spacing: 8) {
                ForEach(category.items, id: \.self) { item in
                    Text(item)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(style.primaryText)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(style.accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(style.cardBorder.opacity(0.45), lineWidth: 1)
        )
    }
}

private struct UnderstandingStepRow: View {
    let guideType: GuideType
    let index: Int
    let text: String

    private var style: GuidePromptStyle {
        GuidePromptStyle.style(for: guideType, emphasis: .standard)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(index)")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(style.primaryText)
                .frame(width: 28, height: 28)
                .background(style.accent.opacity(0.22), in: Circle())
            Text(text)
                .font(.subheadline)
                .foregroundStyle(style.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct UnderstandingBulletRow: View {
    let guideType: GuideType
    let systemImage: String
    let text: String

    private var style: GuidePromptStyle {
        GuidePromptStyle.style(for: guideType, emphasis: .quiet)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(style.accent)
                .padding(.top, 3)
            Text(text)
                .font(.subheadline)
                .foregroundStyle(style.secondaryText)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct UnderstandingSourceGroupCard: View {
    let guideType: GuideType
    let group: UnderstandingSourceGroup

    private var style: GuidePromptStyle {
        GuidePromptStyle.style(for: guideType, emphasis: .quiet)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(group.title)
                .font(.headline)
                .foregroundStyle(style.primaryText)
            if let description = group.description, !description.isEmpty {
                Text(description)
                    .font(.caption)
                    .foregroundStyle(style.secondaryText)
                    .fixedSize(horizontal: false, vertical: true)
            }
            VStack(alignment: .leading, spacing: 8) {
                ForEach(group.sources) { source in
                    UnderstandingSourceLinkRow(
                        guideType: guideType,
                        source: source
                    )
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.03), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .stroke(style.cardBorder.opacity(0.45), lineWidth: 1)
        )
    }
}

private struct UnderstandingSourceLinkRow: View {
    let guideType: GuideType
    let source: UnderstandingSource

    private var style: GuidePromptStyle {
        GuidePromptStyle.style(for: guideType, emphasis: .quiet)
    }

    var body: some View {
        if let url = URL(string: source.url) {
            Link(destination: url) {
                HStack(alignment: .center, spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(source.title)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(style.primaryText)
                            .multilineTextAlignment(.leading)
                        Text(source.label ?? "Learn more")
                            .font(.caption)
                            .foregroundStyle(style.secondaryText)
                    }
                    Spacer()
                    Image(systemName: "arrow.up.right.square")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(style.accent)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(style.accent.opacity(0.08), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
        }
    }
}
