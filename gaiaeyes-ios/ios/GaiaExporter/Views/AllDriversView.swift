import SwiftUI

private struct AllDriversCopy {
    let pageTitle: String
    let subtitle: String
    let activeMetricTitle: String
    let categoryMetricTitle: String
    let stateMetricTitle: String
    let setupHintsTitle: String
    let loadingText: String
    let calmTitle: String
    let calmBody: String
    let learningBody: String

    static func resolve(mode: ExperienceMode, tone: ToneStyle) -> AllDriversCopy {
        let vocabulary = mode.copyVocabulary
        switch mode {
        case .scientific:
            return AllDriversCopy(
                pageTitle: vocabulary.allDriversLabel,
                subtitle: "Current Influences",
                activeMetricTitle: "Active",
                categoryMetricTitle: "Category",
                stateMetricTitle: "State",
                setupHintsTitle: "Ways to sharpen this view",
                loadingText: "Loading current drivers…",
                calmTitle: tone == .humorous ? "Nothing especially loud right now" : "Nothing especially strong right now",
                calmBody: tone.resolveCopy(
                    straight: "Conditions look relatively calm. You can still explore what Gaia Eyes watches for you.",
                    balanced: "Conditions look relatively calm. You can still explore the full driver stack Gaia Eyes is watching.",
                    humorous: "Conditions look relatively calm. The signal pile-up is taking a breather, but the full stack is still here if you want context."
                ),
                learningBody: tone.resolveCopy(
                    straight: "We’re still learning how this tends to line up for you.",
                    balanced: "We’re still learning how these patterns tend to line up for you.",
                    humorous: "We’re still learning your pattern language, so some drivers will stay more observational for now."
                )
            )
        case .mystical:
            return AllDriversCopy(
                pageTitle: vocabulary.allDriversLabel,
                subtitle: "Current Influences",
                activeMetricTitle: "Active",
                categoryMetricTitle: "Category",
                stateMetricTitle: "State",
                setupHintsTitle: "Ways to make this view more personal",
                loadingText: "Loading what’s active right now…",
                calmTitle: tone == .humorous ? "Nothing especially loud right now" : "Nothing especially intense right now",
                calmBody: tone.resolveCopy(
                    straight: "Conditions look relatively calm. You can still explore what Gaia Eyes is tracking.",
                    balanced: "Conditions look relatively calm. You can still explore the full set of influences Gaia Eyes is tracking.",
                    humorous: "Conditions look relatively calm. The field is behaving itself, but the full signal stack is still here if you want context."
                ),
                learningBody: tone.resolveCopy(
                    straight: "We’re still learning how these patterns tend to line up for you.",
                    balanced: "We’re still learning how these patterns tend to line up for you.",
                    humorous: "We’re still learning your pattern language, so some influences will stay more observational for now."
                )
            )
        }
    }
}

struct AllDriversView: View {
    let api: APIClient
    var mode: ExperienceMode = .scientific
    var tone: ToneStyle = .balanced
    var tempUnit: TemperatureUnit = .localeDefault
    var showsCloseButton: Bool = true
    var initialFocusKey: String? = nil
    var signalBar: [SignalPill] = []
    var onOpenCurrentSymptoms: (() -> Void)? = nil
    var onLogSymptoms: (() -> Void)? = nil
    var onOpenPatterns: (() -> Void)? = nil
    var onOpenOutlook: (() -> Void)? = nil
    var onOpenSetup: (() -> Void)? = nil

    @AppStorage("all_drivers_cache_json") private var allDriversCacheJSON: String = ""
    @Environment(\.dismiss) private var dismiss
    @State private var snapshot: AllDriversSnapshot?
    @State private var isLoading: Bool = false
    @State private var errorMessage: String?
    @State private var selectedFilter: DriverCategory = .all
    @State private var expandedDriverID: String?
    @State private var focusedDriverID: String?
    @State private var hasTrackedOpen: Bool = false
    @State private var shareDraft: ShareDraft?

    private var vocabulary: CopyVocabulary {
        mode.copyVocabulary
    }

    private var copy: AllDriversCopy {
        AllDriversCopy.resolve(mode: mode, tone: tone)
    }

    private var filteredDrivers: [DriverDetailItem] {
        let drivers = snapshot?.drivers ?? []
        if selectedFilter == .all {
            return drivers
        }
        return drivers.filter { $0.category == selectedFilter }
    }

    private func translatedLabel(for driver: DriverDetailItem) -> String {
        vocabulary.driverLabel(for: driver.key, fallback: driver.label)
    }

    private func translatedText(_ raw: String?) -> String? {
        vocabulary.presenting(raw)
    }

    private func localizedTemperatureDelta(_ celsius: Double?) -> String {
        guard let celsius else { return "—" }
        let converted = tempUnit == .fahrenheit ? celsius * 9.0 / 5.0 : celsius
        return String(format: "%+.1f %@", converted, tempUnit.symbol)
    }

    private func localizedReading(for driver: DriverDetailItem) -> String? {
        if driver.key == "temp" {
            return localizedTemperatureDelta(driver.readingValue)
        }
        if driver.key == "body_symptoms" {
            let symptomCount = driver.reading?
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
                .count ?? 0
            if symptomCount >= 2 {
                return "\(symptomCount) active"
            }
        }
        return driver.reading
    }

    private func severity(for driver: DriverDetailItem) -> StatusPill.Severity {
        switch stateZoneKey(for: driver) {
        case "high":
            return .alert
        case "elevated":
            return .warn
        default:
            return .ok
        }
    }

    private func stateZoneKey(for driver: DriverDetailItem) -> String {
        switch driver.state {
        case "storm", "strong":
            return "high"
        case "watch", "elevated":
            return "elevated"
        case "active":
            return "mild"
        default:
            return "low"
        }
    }

    private func roleAccent(_ role: DriverRole) -> Color {
        switch role {
        case .leading:
            return GaugePalette.high
        case .supporting:
            return GaugePalette.elevated
        case .background:
            return Color.white.opacity(0.42)
        }
    }

    private func iconName(for driver: DriverDetailItem) -> String {
        switch driver.key {
        case "pressure":
            return "gauge.with.dots.needle.bottom.50percent"
        case "temp":
            return "thermometer.medium"
        case "aqi":
            return "aqi.low"
        case "allergens":
            return "leaf.fill"
        case "kp":
            return "sun.max.fill"
        case "bz":
            return "arrow.down.circle.fill"
        case "solar_wind":
            return "wind"
        case "ulf":
            return "waveform.path.ecg"
        case "flare":
            return "burst.fill"
        case "cme":
            return "sun.haze.fill"
        case "sep":
            return "sparkles"
        case "drap":
            return "antenna.radiowaves.left.and.right"
        case "schumann":
            return "waveform.path.ecg.rectangle"
        default:
            return driver.category == .bodyContext ? "figure.mind.and.body" : "circle.hexagongrid.fill"
        }
    }

    private func formattedUpdate(_ iso: String?) -> String? {
        guard let iso else { return nil }
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: iso) else { return nil }
        let out = DateFormatter()
        out.dateStyle = .medium
        out.timeStyle = .short
        return out.string(from: date)
    }

    private func isExpanded(_ driver: DriverDetailItem) -> Bool {
        expandedDriverID == driver.id
    }

    private func toggle(_ driver: DriverDetailItem) {
        withAnimation(.spring(response: 0.32, dampingFraction: 0.84)) {
            expandedDriverID = expandedDriverID == driver.id ? nil : driver.id
            focusedDriverID = driver.id
        }
        if expandedDriverID == driver.id {
            return
        }
        AppAnalytics.track(
            "all_driver_expanded",
            properties: [
                "driver_key": driver.key,
                "role": driver.role.rawValue,
                "category": driver.category.rawValue,
            ]
        )
    }

    private func applyInitialFocus(from payload: AllDriversSnapshot) {
        guard let initialFocusKey else { return }
        guard let match = payload.drivers.first(where: { $0.matches(focusKey: initialFocusKey) }) else { return }
        expandedDriverID = match.id
        focusedDriverID = match.id
    }

    @MainActor
    private func decodeCachedSnapshot() -> AllDriversSnapshot? {
        guard !allDriversCacheJSON.isEmpty,
              let data = allDriversCacheJSON.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(AllDriversSnapshot.self, from: data)
    }

    @MainActor
    private func hydrateCachedSnapshotIfNeeded() {
        guard snapshot == nil, let cached = decodeCachedSnapshot() else { return }
        snapshot = cached
        errorMessage = nil
    }

    @MainActor
    private func persistSnapshot(_ value: AllDriversSnapshot) {
        guard let data = try? JSONEncoder().encode(value),
              let json = String(data: data, encoding: .utf8) else { return }
        allDriversCacheJSON = json
    }

    private var shouldRefreshOnAppear: Bool {
        guard let raw = snapshot?.asof ?? snapshot?.generatedAt,
              let date = ISO8601DateFormatter().date(from: raw) else { return true }
        return Date().timeIntervalSince(date) > 90
    }

    private func trackOpened(with payload: AllDriversSnapshot) {
        guard !hasTrackedOpen else { return }
        hasTrackedOpen = true
        AppAnalytics.track(
            "all_drivers_opened",
            properties: [
                "count": "\(payload.summary.totalCount)",
                "active_count": "\(payload.summary.activeDriverCount)",
            ]
        )
    }

    private func load(force: Bool = false) async {
        if isLoading {
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let payload = try await api.fetchAllDrivers()
            await MainActor.run {
                snapshot = payload
                persistSnapshot(payload)
                errorMessage = nil
                applyInitialFocus(from: payload)
                trackOpened(with: payload)
            }
        } catch {
            if error is CancellationError { return }
            if let uerr = error as? URLError, uerr.code == .cancelled { return }
            await MainActor.run {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func handleSetupHint(_ hint: DriverSetupHint) {
        if hint.key == "symptoms", let onLogSymptoms {
            AppAnalytics.track("all_drivers_log_symptoms")
            onLogSymptoms()
            return
        }
        onOpenSetup?()
    }

    private func sharePrompt(for accent: ShareAccentLevel) -> String {
        _ = accent
        return "Share"
    }

    private func accentLevel(for severity: String?) -> ShareAccentLevel {
        switch (severity ?? "").lowercased() {
        case "storm", "strong", "high":
            return .storm
        case "elevated":
            return .elevated
        case "watch", "active", "mild":
            return .watch
        default:
            return .calm
        }
    }

    private func spaceVisualURL(_ relativePath: String) -> URL? {
        URL(string: "https://qadwzkwubfbfuslfxkzl.supabase.co/storage/v1/object/public/space-visuals/\(relativePath)")
    }

    private func background(for driver: DriverDetailItem) -> ShareCardBackground {
        switch driver.key {
        case "schumann":
            return ShareCardBackground(
                style: .schumann,
                candidateURLs: [
                    MediaPaths.sanitize("social/earthscope/latest/tomsk_latest.png"),
                    MediaPaths.sanitize("social/earthscope/latest/cumiana_latest.png"),
                ].compactMap { $0 }
            )
        case "cme":
            return ShareCardBackground(
                style: .cme,
                candidateURLs: [
                    spaceVisualURL("nasa/lasco_c2/latest.jpg"),
                    spaceVisualURL("nasa/lasco_c3/latest.jpg"),
                ].compactMap { $0 }
            )
        case "flare", "solar_wind", "kp", "bz", "sep", "drap":
            return ShareCardBackground(
                style: .solar,
                candidateURLs: [
                    spaceVisualURL("nasa/aia_304/latest.jpg"),
                    spaceVisualURL("nasa/geospace_3h/latest.jpg"),
                    spaceVisualURL("drap/latest.png"),
                ].compactMap { $0 }
            )
        case "pressure", "temp", "aqi", "allergens":
            return ShareCardBackground(
                style: .atmospheric,
                candidateURLs: [
                    MediaPaths.sanitize("social/earthscope/backgrounds/checkin.png"),
                    MediaPaths.sanitize("social/earthscope/backgrounds/current_drivers.png"),
                ].compactMap { $0 }
            )
        default:
            return ShareCardBackground(style: .abstract)
        }
    }

    private func signalShareDraft(for driver: DriverDetailItem) -> ShareDraft {
        let translatedReason = translatedText(driver.semanticShortReason) ?? driver.semanticShortReason ?? driver.shortReason
        var bullets: [String] = []
        if let personal = translatedText(driver.semanticPersonalReason), !personal.isEmpty {
            bullets.append(personal)
        }
        if let pattern = translatedText(driver.semanticPatternSummary), !pattern.isEmpty {
            bullets.append(pattern)
        }
        if let outlook = translatedText(driver.semanticOutlookSummary), !outlook.isEmpty {
            bullets.append(outlook)
        }
        if bullets.isEmpty {
            bullets = driver.currentSymptoms.prefix(3).map { "Linked symptom: \($0)" }
        }
        if bullets.isEmpty {
            bullets = ["Worth watching in the broader driver stack."]
        }

        let accent = accentLevel(for: driver.severity ?? driver.state)
        return ShareDraftFactory.signalSnapshot(
            surface: "all_drivers",
            analyticsKey: driver.key,
            mode: mode,
            tone: tone,
            title: translatedLabel(for: driver),
            value: localizedReading(for: driver),
            state: driver.stateLabel ?? driver.state.capitalized,
            interpretation: translatedReason,
            bullets: bullets,
            accent: accent,
            background: background(for: driver),
            sourceLine: driver.sourceHint,
            updatedAt: formattedUpdate(driver.updatedAt ?? driver.asof),
            promptText: sharePrompt(for: accent)
        )
    }

    private func dailyStateShareDraft() -> ShareDraft? {
        guard let snapshot else { return nil }
        let leading = snapshot.drivers.first(where: { $0.role == .leading }) ?? snapshot.drivers.first
        guard let leading else { return nil }
        let supporting = snapshot.drivers
            .filter { $0.id != leading.id }
            .prefix(2)
            .map { translatedLabel(for: $0) }
        let interpretation = translatedText(snapshot.semanticDailyBrief)
            ?? snapshot.semanticDailyBrief
            ?? translatedText(leading.semanticShortReason)
            ?? leading.semanticShortReason
            ?? translatedText(leading.shortReason)
            ?? leading.shortReason
        let accent = accentLevel(for: leading.severity ?? leading.state)
        return ShareDraftFactory.dailyState(
            surface: "all_drivers",
            analyticsKey: leading.key,
            mode: mode,
            title: vocabulary.whatMattersNowLabel,
            leading: translatedLabel(for: leading),
            supporting: supporting,
            interpretation: interpretation,
            accent: accent,
            background: ShareCardBackground(
                style: .abstract,
                candidateURLs: [
                    MediaPaths.sanitize("social/earthscope/backgrounds/current_drivers.png"),
                    MediaPaths.sanitize("social/earthscope/backgrounds/actions.png"),
                ].compactMap { $0 }
            ),
            updatedAt: formattedUpdate(snapshot.asof ?? snapshot.generatedAt),
            promptText: sharePrompt(for: accent)
        )
    }

    private func focusDriver(for signal: SignalPill) {
        let focusKey = signal.driverKey ?? signal.key
        guard let match = snapshot?.drivers.first(where: { $0.matches(focusKey: focusKey) }) else { return }
        AppAnalytics.track("signal_bar_tapped", properties: ["surface": "all_drivers", "signal_key": signal.key])
        withAnimation(.spring(response: 0.32, dampingFraction: 0.84)) {
            selectedFilter = match.category
            expandedDriverID = match.id
            focusedDriverID = match.id
        }
    }

    private var topSummaryCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(copy.pageTitle)
                        .font(.system(size: 30, weight: .bold, design: .rounded))
                        .foregroundColor(.white)
                    Text(copy.subtitle)
                        .font(.subheadline)
                        .foregroundColor(.white.opacity(0.68))
                    if let updated = formattedUpdate(snapshot?.asof ?? snapshot?.generatedAt) {
                        Text("As of \(updated)")
                            .font(.caption)
                            .foregroundColor(.white.opacity(0.52))
                    }
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 8) {
                    if let draft = dailyStateShareDraft() {
                        Button {
                            shareDraft = draft
                        } label: {
                            Label(sharePrompt(for: draft.card.accentLevel), systemImage: "square.and.arrow.up")
                        }
                        .buttonStyle(.bordered)
                        .tint(.white.opacity(0.85))
                    }

                    Button("Refresh") {
                        Task { await load(force: true) }
                    }
                    .buttonStyle(.bordered)
                    .tint(.white.opacity(0.85))
                }
            }

            if let summary = snapshot?.summary {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 10) {
                        SummaryMetric(title: copy.activeMetricTitle, value: "\(summary.activeDriverCount)")
                        SummaryMetric(title: copy.categoryMetricTitle, value: summary.strongestCategory ?? "—")
                        SummaryMetric(title: copy.stateMetricTitle, value: summary.primaryState ?? "—")
                    }
                    if let note = translatedText(snapshot?.semanticDailyBrief) ?? snapshot?.semanticDailyBrief, !note.isEmpty {
                        Text(note)
                            .font(.subheadline.weight(.semibold))
                            .foregroundColor(.white.opacity(0.86))
                    }
                }
            }
        }
        .padding(18)
        .background(
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            Color(red: 0.13, green: 0.17, blue: 0.24),
                            Color(red: 0.07, green: 0.09, blue: 0.13)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        )
        .overlay(
            RoundedRectangle(cornerRadius: 26, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }

    private var setupHintsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(copy.setupHintsTitle)
                .font(.headline)
                .foregroundColor(.white)
            ForEach(snapshot?.setupHints ?? []) { hint in
                Button {
                    handleSetupHint(hint)
                } label: {
                    HStack(alignment: .top, spacing: 10) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(translatedText(hint.label) ?? hint.label)
                                .font(.subheadline.weight(.semibold))
                                .foregroundColor(.white)
                            Text(translatedText(hint.reason) ?? hint.reason)
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.68))
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer()
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .foregroundColor(.white.opacity(0.42))
                    }
                    .padding(12)
                    .background(Color.white.opacity(0.04))
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.03))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(Color.white.opacity(0.06), lineWidth: 1)
        )
    }

    private var emptyStateCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(copy.calmTitle)
                .font(.title3.weight(.bold))
                .foregroundColor(.white)
            Text(copy.calmBody)
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.68))
            if snapshot?.hasPersonalPatterns != true {
                Text(copy.learningBody)
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.52))
            }
        }
        .padding(18)
        .background(Color.white.opacity(0.04))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(Color.white.opacity(0.06), lineWidth: 1)
        )
    }

    var body: some View {
        ZStack {
            LinearGradient(
                colors: [
                    Color(red: 0.03, green: 0.04, blue: 0.06),
                    Color(red: 0.05, green: 0.06, blue: 0.09),
                    Color(red: 0.02, green: 0.03, blue: 0.05)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 16) {
                        topSummaryCard

                        if let cleanError = errorMessage?.trimmingCharacters(in: .whitespacesAndNewlines), !cleanError.isEmpty {
                            Text(cleanError)
                                .font(.caption)
                                .foregroundColor(.orange)
                        }

                        DriverCategoryFilterView(
                            selectedFilter: $selectedFilter,
                            filters: snapshot?.filters ?? []
                        )

                        if isLoading && snapshot == nil {
                            ProgressView(copy.loadingText)
                                .tint(.white)
                                .frame(maxWidth: .infinity, alignment: .center)
                                .padding(.vertical, 28)
                        } else {
                            if (snapshot?.summary.activeDriverCount ?? 0) == 0 {
                                emptyStateCard
                            }

                            if let snapshot, !snapshot.setupHints.isEmpty {
                                setupHintsCard
                            }

                            if filteredDrivers.isEmpty {
                                emptyStateCard
                            } else {
                                ForEach(filteredDrivers) { driver in
                                    VStack(alignment: .leading, spacing: 0) {
                                        DriverRowView(
                                            driver: driver,
                                            readingText: localizedReading(for: driver),
                                            translatedLabel: translatedLabel(for: driver),
                                            stateSeverity: severity(for: driver),
                                            roleAccent: roleAccent(driver.role),
                                            iconName: iconName(for: driver),
                                            zoneKey: stateZoneKey(for: driver),
                                            isExpanded: isExpanded(driver),
                                            translatedShortReason: translatedText(driver.semanticShortReason) ?? driver.semanticShortReason
                                        ) {
                                            toggle(driver)
                                        }

                                        if isExpanded(driver) {
                                            DriverExpandedDetailView(
                                                driver: driver,
                                                mode: mode,
                                                tone: tone,
                                                translatedPatternSummary: translatedText(driver.semanticPatternSummary) ?? driver.semanticPatternSummary,
                                                translatedOutlookSummary: translatedText(driver.semanticOutlookSummary) ?? driver.semanticOutlookSummary,
                                                translatedScienceNote: translatedText(driver.scienceNote),
                                                sharePrompt: sharePrompt(for: accentLevel(for: driver.severity ?? driver.state)),
                                                onShare: {
                                                    shareDraft = signalShareDraft(for: driver)
                                                },
                                                onOpenCurrentSymptoms: onOpenCurrentSymptoms == nil ? nil : {
                                                    AppAnalytics.track("all_drivers_symptom_cta", properties: ["driver_key": driver.key])
                                                    onOpenCurrentSymptoms?()
                                                },
                                                onLogSymptoms: onLogSymptoms == nil ? nil : {
                                                    AppAnalytics.track("all_drivers_log_symptoms", properties: ["driver_key": driver.key])
                                                    onLogSymptoms?()
                                                },
                                                onOpenPatterns: onOpenPatterns == nil ? nil : {
                                                    AppAnalytics.track("all_drivers_pattern_cta", properties: ["driver_key": driver.key])
                                                    onOpenPatterns?()
                                                },
                                                onOpenOutlook: onOpenOutlook == nil ? nil : {
                                                    AppAnalytics.track("all_drivers_outlook_cta", properties: ["driver_key": driver.key])
                                                    onOpenOutlook?()
                                                }
                                            )
                                        }
                                    }
                                    .id(driver.id)
                                    .background(
                                        RoundedRectangle(cornerRadius: 24, style: .continuous)
                                            .fill(Color.white.opacity(driver.role == .background ? 0.025 : 0.045))
                                    )
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 24, style: .continuous)
                                            .stroke(Color.white.opacity(driver.role == .leading ? 0.12 : 0.06), lineWidth: 1)
                                    )
                                    .shadow(
                                        color: GaugePalette.zoneColor(stateZoneKey(for: driver)).opacity(driver.role == .leading ? 0.18 : 0.0),
                                        radius: driver.role == .leading ? 16 : 0,
                                        x: 0,
                                        y: 0
                                    )
                                }
                            }
                        }
                    }
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .task {
                    await MainActor.run {
                        hydrateCachedSnapshotIfNeeded()
                        if let snapshot {
                            applyInitialFocus(from: snapshot)
                            trackOpened(with: snapshot)
                        }
                    }
                    if snapshot == nil || shouldRefreshOnAppear {
                        await load()
                    }
                }
                .refreshable {
                    await load(force: true)
                }
                .onChange(of: selectedFilter, initial: false) { _, newValue in
                    AppAnalytics.track("all_drivers_filter_changed", properties: ["filter": newValue.rawValue])
                }
                .onChange(of: focusedDriverID, initial: false) { _, newValue in
                    guard let newValue else { return }
                    withAnimation(.spring(response: 0.34, dampingFraction: 0.86)) {
                        proxy.scrollTo(newValue, anchor: .top)
                    }
                }
            }
        }
        .navigationTitle(copy.pageTitle)
        .navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .top) {
            SignalBarView(signals: signalBar, onTap: focusDriver(for:))
        }
        .toolbar {
            if showsCloseButton {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") {
                        dismiss()
                    }
                }
            }
        }
        .sheet(item: $shareDraft) { draft in
            SharePreviewView(draft: draft)
        }
    }
}

private struct SummaryMetric: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title.uppercased())
                .font(.caption2.weight(.semibold))
                .foregroundColor(.white.opacity(0.48))
            Text(value)
                .font(.subheadline.weight(.semibold))
                .foregroundColor(.white.opacity(0.9))
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.white.opacity(0.05))
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

private struct DriverCategoryFilterView: View {
    @Binding var selectedFilter: DriverCategory
    let filters: [DriverFilterOption]

    private var displayFilters: [DriverFilterOption] {
        if filters.isEmpty {
            return [
                DriverFilterOption(key: .all, label: "All"),
                DriverFilterOption(key: .space, label: "Space"),
                DriverFilterOption(key: .earth, label: "Earth / Resonance"),
                DriverFilterOption(key: .local, label: "Local"),
                DriverFilterOption(key: .bodyContext, label: "Body Context"),
            ]
        }
        return filters
    }

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(displayFilters) { filter in
                    let isSelected = selectedFilter == filter.key
                    Button(filter.label) {
                        withAnimation(.spring(response: 0.28, dampingFraction: 0.84)) {
                            selectedFilter = filter.key
                        }
                    }
                    .buttonStyle(.plain)
                    .font(.caption.weight(.semibold))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .background(isSelected ? Color.white.opacity(0.14) : Color.white.opacity(0.05))
                    .overlay(
                        Capsule()
                            .stroke(isSelected ? Color.white.opacity(0.22) : Color.white.opacity(0.08), lineWidth: 1)
                    )
                    .clipShape(Capsule())
                    .foregroundColor(.white)
                }
            }
        }
    }
}

private struct DriverRowView: View {
    let driver: DriverDetailItem
    let readingText: String?
    let translatedLabel: String
    let stateSeverity: StatusPill.Severity
    let roleAccent: Color
    let iconName: String
    let zoneKey: String
    let isExpanded: Bool
    let translatedShortReason: String?
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 14) {
                ZStack {
                    Circle()
                        .fill(GaugePalette.zoneColor(zoneKey).opacity(0.16))
                        .frame(width: 40, height: 40)
                    Image(systemName: iconName)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(GaugePalette.zoneColor(zoneKey))
                }

                VStack(alignment: .leading, spacing: 8) {
                    HStack(alignment: .top, spacing: 8) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(translatedLabel)
                                .font(.headline)
                                .foregroundColor(.white)
                                .multilineTextAlignment(.leading)
                            Text(driver.roleLabel ?? driver.role.rawValue.capitalized)
                                .font(.caption.weight(.semibold))
                                .foregroundColor(roleAccent)
                        }
                        Spacer(minLength: 8)
                        VStack(alignment: .trailing, spacing: 6) {
                            StatusPill(driver.stateLabel ?? driver.state.capitalized, severity: stateSeverity)
                            if let reading = readingText, !reading.isEmpty {
                                Text(reading)
                                    .font(.caption.weight(.semibold))
                                    .foregroundColor(.white.opacity(0.64))
                                    .multilineTextAlignment(.trailing)
                                    .lineLimit(2)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .frame(maxWidth: 96, alignment: .trailing)
                    }

                    if let translatedShortReason, !translatedShortReason.isEmpty {
                        Text(translatedShortReason)
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.72))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                    .font(.caption.weight(.bold))
                    .foregroundColor(.white.opacity(0.44))
                    .padding(.top, 6)
            }
            .padding(16)
        }
        .buttonStyle(.plain)
    }
}

private struct DriverExpandedDetailView: View {
    let driver: DriverDetailItem
    let mode: ExperienceMode
    let tone: ToneStyle
    let translatedPatternSummary: String?
    let translatedOutlookSummary: String?
    let translatedScienceNote: String?
    let sharePrompt: String?
    let onShare: (() -> Void)?
    let onOpenCurrentSymptoms: (() -> Void)?
    let onLogSymptoms: (() -> Void)?
    let onOpenPatterns: (() -> Void)?
    let onOpenOutlook: (() -> Void)?

    private var noPatternText: String {
        switch tone {
        case .straight:
            return "We’re still learning how this tends to line up for you."
        case .balanced:
            return "We’re still learning how this tends to line up for you."
        case .humorous:
            return "We’re still building the receipts on how this usually lands for you."
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let onShare {
                Button(sharePrompt ?? "Share") {
                    onShare()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }

            DriverPatternBadgeView(
                statusLabel: driver.patternStatusLabel ?? driver.patternStatus?.rawValue.replacingOccurrences(of: "_", with: " ").capitalized ?? "No clear pattern yet",
                summary: translatedPatternSummary ?? noPatternText,
                evidenceCount: driver.patternEvidenceCount,
                lagHours: driver.patternLagHours,
                onOpenPatterns: onOpenPatterns
            )

            if let translatedOutlookSummary, !translatedOutlookSummary.isEmpty {
                DriverOutlookRelevanceView(
                    label: driver.outlookRelevance,
                    summary: translatedOutlookSummary,
                    onOpenOutlook: onOpenOutlook
                )
            }

            DriverSymptomLinkView(
                currentSymptoms: driver.currentSymptoms,
                historicalSymptoms: driver.historicalSymptoms,
                onOpenCurrentSymptoms: onOpenCurrentSymptoms,
                onLogSymptoms: onLogSymptoms
            )

            if let translatedScienceNote, !translatedScienceNote.isEmpty, mode == .scientific {
                detailSection("Science note", text: translatedScienceNote)
            }
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 16)
    }

    @ViewBuilder
    private func detailSection(_ title: String, text: String?) -> some View {
        if let text, !text.isEmpty {
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.white.opacity(0.52))
                    .textCase(.uppercase)
                Text(text)
                    .font(.subheadline)
                    .foregroundColor(.white.opacity(0.78))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

private struct DriverPatternBadgeView: View {
    let statusLabel: String
    let summary: String
    let evidenceCount: Int?
    let lagHours: Int?
    let onOpenPatterns: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Pattern context")
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.white.opacity(0.52))
                    .textCase(.uppercase)
                Spacer()
                StatusPill(statusLabel, severity: severity)
            }

            Text(summary)
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.78))
                .fixedSize(horizontal: false, vertical: true)

            if evidenceCount != nil || lagHours != nil {
                Text(evidenceLine)
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.56))
            }

            if let onOpenPatterns {
                Button("View pattern detail") {
                    onOpenPatterns()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
    }

    private var severity: StatusPill.Severity {
        let raw = statusLabel.lowercased()
        if raw.contains("strong") {
            return .alert
        }
        if raw.contains("moderate") || raw.contains("emerging") {
            return .warn
        }
        return .ok
    }

    private var evidenceLine: String {
        var bits: [String] = []
        if let evidenceCount {
            bits.append("\(evidenceCount) active links")
        }
        if let lagHours {
            bits.append("Lag \(lagHours)h")
        }
        return bits.joined(separator: " • ")
    }
}

private struct DriverSymptomLinkView: View {
    let currentSymptoms: [String]
    let historicalSymptoms: [String]
    let onOpenCurrentSymptoms: (() -> Void)?
    let onLogSymptoms: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Symptoms linked")
                .font(.caption.weight(.semibold))
                .foregroundColor(.white.opacity(0.52))
                .textCase(.uppercase)

            if !currentSymptoms.isEmpty {
                symptomRow(title: "Active right now", values: currentSymptoms)
            }
            if !historicalSymptoms.isEmpty {
                symptomRow(title: "Appeared before", values: historicalSymptoms)
            }
            if currentSymptoms.isEmpty && historicalSymptoms.isEmpty {
                Text("We’re still learning which symptoms tend to appear alongside this for you.")
                    .font(.subheadline)
                    .foregroundColor(.white.opacity(0.72))
            }

            HStack(spacing: 10) {
                if let onOpenCurrentSymptoms {
                    Button("View current symptoms") {
                        onOpenCurrentSymptoms()
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
                if let onLogSymptoms {
                    Button("Log how you feel") {
                        onLogSymptoms()
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
        }
    }

    @ViewBuilder
    private func symptomRow(title: String, values: [String]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundColor(.white.opacity(0.56))
            Text(values.joined(separator: " • "))
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.78))
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct DriverOutlookRelevanceView: View {
    let label: String?
    let summary: String
    let onOpenOutlook: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Outlook relevance")
                    .font(.caption.weight(.semibold))
                    .foregroundColor(.white.opacity(0.52))
                    .textCase(.uppercase)
                Spacer()
                if let label, !label.isEmpty {
                    StatusPill(label.uppercased(), severity: .warn)
                }
            }

            Text(summary)
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.78))
                .fixedSize(horizontal: false, vertical: true)

            if let onOpenOutlook {
                Button("Open outlook") {
                    onOpenOutlook()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
    }
}
