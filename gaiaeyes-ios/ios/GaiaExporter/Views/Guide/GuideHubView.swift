import SwiftUI

enum GuideHubFocus: String, Hashable {
    case overview
    case dailyCheckIn
    case dailyPoll
    case earthScope
    case understanding
}

struct GuideHubView: View {
    @ObservedObject var profileStore: GuideProfileStore
    let api: APIClient
    let helpContext: HelpCenterContext
    let dailyCheckInStatus: DailyCheckInStatus?
    let dailyCheckInLoading: Bool
    let dailyCheckInError: String?
    let currentSymptomsSnapshot: CurrentSymptomsSnapshot?
    let possibleSymptomsSummary: String?
    let earthscopeSummary: String?
    let earthscopeUpdatedAt: String?
    let supportItems: [DashboardSupportItem]
    let earthInfluences: [String]
    let spaceInfluences: [String]
    let bodyInfluences: [String]
    let whatMattersNow: [String]
    let whatMattersSummary: String?
    var initialFocus: GuideHubFocus = .overview
    let onRefreshDailyCheckIn: () -> Void
    let onOpenEarthScope: () -> Void
    let onOpenCurrentSymptoms: () -> Void
    let onOpenSettings: () -> Void
    let onOpenNotifications: () -> Void
    let onOpenAllDrivers: () -> Void
    let onDailyCheckInStatusChanged: (DailyCheckInStatus) -> Void

    @State private var navigationPath: [GuideHubRoute] = []
    @Environment(\.dismiss) private var dismiss

    @AppStorage("guide.daily_poll.day") private var storedPollDay: String = ""
    @AppStorage("guide.daily_poll.prompt_id") private var storedPollPromptID: String = ""
    @AppStorage("guide.daily_poll.answer_id") private var storedPollAnswerID: String = ""
    @AppStorage("guide.daily_poll.answer_title") private var storedPollAnswerTitle: String = ""

    private enum GuideHubRoute: Hashable {
        case dailyCheckIn
        case understanding
        case helpCenter
    }

    private struct GuideDailyPollChoice: Identifiable, Hashable {
        let id: String
        let title: String
    }

    private struct GuideDailyPollPrompt: Hashable {
        let id: String
        let day: String
        let question: String
        let supportingText: String
        let choices: [GuideDailyPollChoice]
    }

    private var profile: GuideProfile {
        profileStore.profile
    }

    private var style: GuidePromptStyle {
        GuidePromptStyle.style(for: profile.guideType, emphasis: .standard)
    }

    private var followUpItem: CurrentSymptomItem? {
        currentSymptomsSnapshot?.items.first(where: { $0.pendingFollowUp != nil })
    }

    private var followUpMessage: String {
        if let followUpItem {
            return "You have a follow-up waiting for \(followUpItem.label.lowercased()). Open Body to respond in the real symptom workflow."
        }
        if let summary = currentSymptomsSnapshot?.semanticFollowUpSummary {
            return summary
        }
        return GuidePromptStyle.followUpFallbackMessage(for: profile)
    }

    private var dailyCheckInCardBadge: String? {
        if dailyCheckInLoading {
            return "Checking"
        }
        if let error = sanitizedError(dailyCheckInError) {
            return error
        }
        if isDailyCheckInCompleted {
            return "Done"
        }
        if dailyCheckInStatus?.prompt != nil {
            return "Ready"
        }
        return dailyCheckInStatus?.settings.enabled == true ? "Waiting" : "Off"
    }

    private var isDailyCheckInCompleted: Bool {
        guard
            let promptDay = dailyCheckInStatus?.targetDay ?? dailyCheckInStatus?.prompt?.day,
            let completedAt = dailyCheckInStatus?.latestEntry?.completedAt,
            !completedAt.isEmpty
        else {
            return false
        }
        return dailyCheckInStatus?.latestEntry?.day == promptDay
    }

    private var dailyCheckInBody: String {
        if let error = sanitizedError(dailyCheckInError) {
            return error
        }
        if dailyCheckInLoading {
            return "I’m checking whether today’s feedback prompt is ready."
        }
        if isDailyCheckInCompleted {
            if let exposureSummary = dailyCheckInStatus?.latestEntry?.summaryExposureText {
                return "Today’s check-in is already logged. Also noted: \(exposureSummary). You can reopen it if you want to review or update the entry."
            }
            return "Today’s check-in is already logged. You can reopen it if you want to review or update the entry."
        }
        if let prompt = dailyCheckInStatus?.prompt {
            return prompt.questionText
        }
        if dailyCheckInStatus?.settings.enabled == true {
            return "Your daily check-in will surface here as soon as Gaia Eyes has the right moment to ask."
        }
        return "Daily check-ins are off right now. You can turn them on in notification settings."
    }

    private var earthscopeBody: String {
        if !influenceSections.isEmpty {
            return "These are the strongest earth, space, and body influences standing out in today’s read."
        }
        if let summary = earthscopeSummary?.trimmingCharacters(in: .whitespacesAndNewlines), !summary.isEmpty {
            return summary
        }
        if let summary = whatMattersSummary?.trimmingCharacters(in: .whitespacesAndNewlines), !summary.isEmpty {
            return summary
        }
        if !whatMattersNow.isEmpty {
            return "What’s standing out right now: \(whatMattersNow.prefix(2).joined(separator: ", "))."
        }
        return GuidePromptStyle.earthscopeFallbackMessage(for: profile)
    }

    private var guideOverviewSummary: String? {
        let candidates = [
            possibleSymptomsSummary,
            whatMattersSummary,
            currentSymptomsSnapshot?.semanticHeaderSummary,
            earthscopeSummary,
        ]
        for candidate in candidates {
            let trimmed = candidate?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !trimmed.isEmpty {
                return trimmed
            }
        }
        return nil
    }

    private var guideTopLine: String {
        GuidePromptStyle.headerSupportLine(for: profile)
    }

    private var possibleSymptomsBody: String {
        let summary = guideOverviewSummary?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !summary.isEmpty {
            return summary
        }
        return GuidePromptStyle.headerLine(for: profile)
    }

    private var influenceSections: [(title: String, items: [String])] {
        [
            ("Earth influences", Array(earthInfluences.prefix(3))),
            ("Space influences", Array(spaceInfluences.prefix(3))),
            ("Body influences", Array(bodyInfluences.prefix(3))),
        ].filter { !$0.items.isEmpty }
    }

    private var curatedSupportItems: [DashboardSupportItem] {
        var chosen: [DashboardSupportItem] = []
        var seenPrefixes: Set<String> = []

        for item in supportItems {
            let prefix = supportActionPrefix(for: item)
            if let prefix, seenPrefixes.contains(prefix) {
                continue
            }
            chosen.append(item)
            if let prefix {
                seenPrefixes.insert(prefix)
            }
            if chosen.count >= 3 {
                break
            }
        }

        return chosen
    }

    private var dailyPollSupportText: String {
        let context: GuidePromptStyle.DailyPollContext
        if todayPollPrompt.id.hasPrefix("followup:") {
            context = .followUp
        } else if todayPollPrompt.id.hasPrefix("symptom:") {
            context = .symptomPulse
        } else {
            context = .compareDay
        }
        return GuidePromptStyle.dailyPollSupportLine(for: profile, context: context)
    }

    private var earthscopeBadge: String? {
        asofText(earthscopeUpdatedAt)
    }

    private var todayPollPrompt: GuideDailyPollPrompt {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.dateFormat = "yyyy-MM-dd"
        let today = dailyCheckInStatus?.targetDay ?? dailyCheckInStatus?.prompt?.day ?? formatter.string(from: Date())

        if let followUpItem {
            return GuideDailyPollPrompt(
                id: "followup:\(followUpItem.id)",
                day: today,
                question: "Did \(followUpItem.label.lowercased()) stand out today?",
                supportingText: "A quick pulse keeps Guide Hub useful without asking for a full check-in.",
                choices: [
                    GuideDailyPollChoice(id: "yes", title: "Yes"),
                    GuideDailyPollChoice(id: "a_little", title: "A little"),
                    GuideDailyPollChoice(id: "not_really", title: "Not really")
                ]
            )
        }

        if let label = dailyCheckInStatus?.prompt?.activeSymptomLabels.first {
            return GuideDailyPollPrompt(
                id: "symptom:\(label.lowercased())",
                day: today,
                question: "Did \(label.lowercased()) shape the day more than expected?",
                supportingText: "This stays lighter than the full check-in and is ready for future guide feedback logic.",
                choices: [
                    GuideDailyPollChoice(id: "yes", title: "Yes"),
                    GuideDailyPollChoice(id: "somewhat", title: "Somewhat"),
                    GuideDailyPollChoice(id: "no", title: "No")
                ]
            )
        }

        return GuideDailyPollPrompt(
            id: "daily_compare",
            day: today,
            question: "Did today feel better or worse than yesterday?",
            supportingText: "A fast answer here keeps the guide loop alive even when you skip the longer check-in.",
            choices: [
                GuideDailyPollChoice(id: "better", title: "Better"),
                GuideDailyPollChoice(id: "same", title: "About the same"),
                GuideDailyPollChoice(id: "worse", title: "Worse")
            ]
        )
    }

    private var hasPollResponseForToday: Bool {
        storedPollDay == todayPollPrompt.day &&
        storedPollPromptID == todayPollPrompt.id &&
        !storedPollAnswerID.isEmpty
    }

    var body: some View {
        NavigationStack(path: $navigationPath) {
            ScrollViewReader { proxy in
                ScrollView {
                    contentStack
                }
                .background(Color.black.opacity(0.97).ignoresSafeArea())
                .navigationTitle("Guide")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Close") { dismiss() }
                    }
                }
                .navigationDestination(for: GuideHubRoute.self) { route in
                    switch route {
                    case .dailyCheckIn:
                        DailyCheckInView(
                            api: api,
                            mode: profile.mode,
                            tone: profile.tone,
                            initialStatus: dailyCheckInStatus,
                            onStatusChanged: onDailyCheckInStatusChanged
                        )
                    case .understanding:
                        UnderstandingGaiaEyesView(profile: profile)
                    case .helpCenter:
                        if let category = HelpCenterContent.shared.category(id: "understanding-gaia-eyes") {
                            HelpCategoryView(category: category, document: HelpCenterContent.shared, context: helpContext)
                        } else {
                            HelpCenterView(context: helpContext)
                        }
                    }
                }
                .task {
                    if dailyCheckInStatus == nil && !dailyCheckInLoading {
                        onRefreshDailyCheckIn()
                    }
                    await MainActor.run {
                        switch initialFocus {
                        case .dailyCheckIn:
                            proxy.scrollTo(GuideHubFocus.dailyCheckIn, anchor: .top)
                        case .dailyPoll:
                            proxy.scrollTo(GuideHubFocus.dailyPoll, anchor: .top)
                        case .earthScope:
                            proxy.scrollTo(GuideHubFocus.earthScope, anchor: .top)
                        case .understanding:
                            proxy.scrollTo(GuideHubFocus.understanding, anchor: .top)
                        case .overview:
                            break
                        }
                    }
                }
            }
        }
    }

    private var contentStack: some View {
        VStack(alignment: .leading, spacing: 18) {
            headerCard
                .id(GuideHubFocus.overview)

            earthscopeCard
                .id(GuideHubFocus.earthScope)

            if !curatedSupportItems.isEmpty {
                supportCard
            }

            dailyCheckInCard
                .id(GuideHubFocus.dailyCheckIn)

            dailyPollCard
                .id(GuideHubFocus.dailyPoll)

            followUpCard

            understandingCard
                .id(GuideHubFocus.understanding)
        }
        .padding(16)
    }

    private var dailyCheckInCard: some View {
        GuideHubSectionCard(
            guideType: profile.guideType,
            expression: .curious,
            emphasis: .standard,
            eyebrow: "Daily Check-In",
            title: "Check in with the day",
            message: dailyCheckInBody,
            badgeText: dailyCheckInCardBadge,
            primaryActionTitle: "Open check-in",
            primaryAction: { navigationPath.append(.dailyCheckIn) }
        ) {
            if let labels = dailyCheckInStatus?.prompt?.activeSymptomLabels, !labels.isEmpty {
                wrappingHighlightList(Array(labels.prefix(3)))
            }
        }
    }

    private var dailyPollCard: some View {
        GuideHubSectionCard(
            guideType: profile.guideType,
            expression: .followUp,
            emphasis: hasPollResponseForToday ? .quiet : .standard,
            eyebrow: "Daily Poll",
            title: "A faster pulse question",
            message: todayPollPrompt.question,
            badgeText: hasPollResponseForToday ? "Saved" : "Quick",
            content: {
            VStack(alignment: .leading, spacing: 10) {
                Text(dailyPollSupportText)
                    .font(.caption)
                    .foregroundStyle(style.secondaryText)
                if hasPollResponseForToday {
                    Text(storedPollAnswerTitle.isEmpty ? "Saved for today." : "Saved for today: \(storedPollAnswerTitle)")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(style.primaryText)
                } else {
                    HStack(spacing: 10) {
                        ForEach(todayPollPrompt.choices) { choice in
                            Button(choice.title) {
                                savePollResponse(choice: choice, prompt: todayPollPrompt)
                            }
                            .buttonStyle(.bordered)
                            .tint(style.accent)
                        }
                    }
                }
            }
            }
        )
    }

    private var earthscopeCard: some View {
        GuideHubSectionCard(
            guideType: profile.guideType,
            expression: .helpful,
            emphasis: .elevated,
            eyebrow: "Why",
            title: "Today's possible influences",
            message: earthscopeBody,
            badgeText: earthscopeBadge,
            secondaryActionTitle: "All drivers",
            secondaryAction: onOpenAllDrivers
        ) {
            if !influenceSections.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(Array(influenceSections.enumerated()), id: \.offset) { _, section in
                        influenceSection(title: section.title, items: section.items)
                    }
                }
            } else if !whatMattersNow.isEmpty {
                wrappingHighlightList(Array(whatMattersNow.prefix(3)))
            }
        }
    }

    private var followUpCard: some View {
        GuideHubSectionCard(
            guideType: profile.guideType,
            expression: .helpful,
            emphasis: followUpItem == nil ? .quiet : .standard,
            eyebrow: "Follow-Ups",
            title: followUpItem == nil ? "Nothing is waiting right now" : "A symptom follow-up is waiting",
            message: followUpMessage,
            badgeText: followUpItem == nil ? "Future-ready" : "Active",
            primaryActionTitle: "Open Body context",
            primaryAction: onOpenCurrentSymptoms
        )
    }

    private var supportCard: some View {
        let primary = curatedSupportItems.first
        let additional = Array(curatedSupportItems.dropFirst())

        return GuideHubSectionCard(
            guideType: profile.guideType,
            expression: guideSupportExpression(for: primary?.tone),
            emphasis: guideSupportEmphasis(for: primary?.tone),
            eyebrow: "Support right now",
            title: primary?.title ?? "A steadier lane for today",
            message: primary?.message ?? "Keep the basics steady and use a gentler pace if your body is asking for more margin.",
            badgeText: primary?.badge,
            primaryActionTitle: "Open Body context",
            primaryAction: onOpenCurrentSymptoms,
            secondaryActionTitle: "All drivers",
            secondaryAction: onOpenAllDrivers
        ) {
            VStack(alignment: .leading, spacing: 10) {
                if let primary, let actions = primary.actions, !actions.isEmpty {
                    wrappingHighlightList(actions)
                }
                if !additional.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(additional) { item in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack(spacing: 8) {
                                    Text(item.title)
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(style.primaryText)
                                    if let badge = item.badge, !badge.isEmpty {
                                        Text(badge)
                                            .font(.caption2.weight(.semibold))
                                            .foregroundStyle(style.primaryText)
                                            .padding(.horizontal, 8)
                                            .padding(.vertical, 4)
                                            .background(style.accent.opacity(0.18))
                                            .clipShape(Capsule())
                                    }
                                }
                                Text(item.message)
                                    .font(.caption)
                                    .foregroundStyle(style.secondaryText)
                                if let actions = item.actions, !actions.isEmpty {
                                    wrappingHighlightList(Array(actions.prefix(2)))
                                }
                            }
                            .padding(.top, 2)
                        }
                    }
                }
            }
        }
    }

    private var understandingCard: some View {
        GuideHubSectionCard(
            guideType: profile.guideType,
            expression: .guide,
            emphasis: .standard,
            eyebrow: "Help and Understanding",
            title: "Start with the basics",
            message: GuidePromptStyle.understandingCardMessage(for: profile),
            primaryActionTitle: "Open help center",
            primaryAction: { navigationPath.append(.helpCenter) },
            secondaryActionTitle: "Deep dive",
            secondaryAction: { navigationPath.append(.understanding) }
        )
    }

    private func guideSupportExpression(for tone: String?) -> GuideExpression {
        switch tone?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "high", "watch":
            return .alert
        case "mild":
            return .helpful
        default:
            return .calm
        }
    }

    private func guideSupportEmphasis(for tone: String?) -> GuideAvatarEmphasis {
        switch tone?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "high", "watch":
            return .elevated
        case "mild":
            return .standard
        default:
            return .quiet
        }
    }

    private var headerCard: some View {
        let headerStyle = GuidePromptStyle.style(for: profile.guideType, emphasis: .elevated)

        return VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 16) {
                GuideAvatarView(
                    guide: profile.guideType,
                    expression: .guide,
                    size: .large,
                    emphasis: .elevated,
                    showBackingPlate: false,
                    showGlow: false,
                    sizeMultiplier: 1.3,
                    animate: true
                )

                VStack(alignment: .leading, spacing: 6) {
                    Text("Possible symptoms today")
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                        .foregroundStyle(headerStyle.primaryText)
                    Text(guideTopLine)
                        .font(.subheadline)
                        .foregroundStyle(headerStyle.tertiaryText)
                    Text(possibleSymptomsBody)
                        .font(.headline)
                        .foregroundStyle(headerStyle.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("\(profile.guideType.title) • \(profile.mode.title) • \(profile.tone.title)")
                        .font(.caption)
                        .foregroundStyle(headerStyle.tertiaryText)
                }
                Spacer(minLength: 0)
                Button(action: onOpenSettings) {
                    Image(systemName: "gearshape.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(headerStyle.primaryText)
                        .frame(width: 38, height: 38)
                        .background(headerStyle.accent.opacity(0.22), in: Circle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(headerStyle.cardFill, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(headerStyle.cardBorder, lineWidth: 1)
        )
        .shadow(color: headerStyle.glow, radius: 16)
    }

    private func influenceSection(title: String, items: [String]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(style.tertiaryText)
            VStack(alignment: .leading, spacing: 6) {
                ForEach(items, id: \.self) { item in
                    HStack(alignment: .top, spacing: 8) {
                        Circle()
                            .fill(style.accent.opacity(0.92))
                            .frame(width: 6, height: 6)
                            .padding(.top, 6)
                        Text(item)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(style.primaryText)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    private func wrappingHighlightList(_ items: [String]) -> some View {
        let rowStyle = GuidePromptStyle.style(for: profile.guideType, emphasis: .quiet)
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(items, id: \.self) { item in
                Text(item)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(rowStyle.primaryText)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(rowStyle.accent.opacity(0.16), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func supportActionPrefix(for item: DashboardSupportItem) -> String? {
        guard let action = item.actions?.first?.trimmingCharacters(in: .whitespacesAndNewlines), !action.isEmpty else {
            return nil
        }
        let lowered = action.lowercased()
        let words = lowered.split(whereSeparator: \.isWhitespace)
        guard !words.isEmpty else { return nil }
        return words.prefix(2).joined(separator: " ")
    }

    private func savePollResponse(choice: GuideDailyPollChoice, prompt: GuideDailyPollPrompt) {
        storedPollDay = prompt.day
        storedPollPromptID = prompt.id
        storedPollAnswerID = choice.id
        storedPollAnswerTitle = choice.title
    }

    private func sanitizedError(_ error: String?) -> String? {
        guard let raw = error?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        return raw
    }

    private func asofText(_ iso: String?) -> String? {
        guard let iso else { return nil }
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: iso) else { return nil }
        return DateFormatter.localizedString(from: date, dateStyle: .medium, timeStyle: .short)
    }
}
