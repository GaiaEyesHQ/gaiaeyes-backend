import SwiftUI

struct SymptomPreset: Identifiable, Hashable {
    let id: String
    let code: String
    let label: String
    let systemImage: String
    let tags: [String]?

    init(code: String, label: String, systemImage: String? = nil, tags: [String]? = nil) {
        let normalizedCode = normalize(code)
        self.id = normalizedCode
        self.code = normalizedCode
        self.label = label
        self.systemImage = systemImage ?? SymptomPreset.defaultSystemImage(for: normalizedCode)
        self.tags = tags
    }

    init(definition: SymptomCodeDefinition) {
        let normalizedCode = normalize(definition.symptomCode)
        id = normalizedCode
        code = normalizedCode
        let trimmedLabel = definition.label.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmedLabel.isEmpty {
            label = normalizedCode.replacingOccurrences(of: "_", with: " ").capitalized
        } else {
            label = trimmedLabel
        }
        let icon = definition.systemImage?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        systemImage = icon.isEmpty ? SymptomPreset.defaultSystemImage(for: normalizedCode) : icon
        tags = definition.tags
    }

    private static func defaultSystemImage(for code: String) -> String {
        switch code {
        case "NERVE_PAIN": return "bolt.heart"
        case "ZAPS": return "bolt"
        case "NAUSEA": return "mouth"
        case "BLOATING": return "circle.dotted"
        case "STOMACH_PAIN": return "cross.case"
        case "REFLUX": return "flame"
        case "DIGESTIVE_UPSET": return "cross.case.fill"
        case "BOWEL_URGENCY": return "figure.walk.motion"
        case "DRAINED": return "battery.25"
        case "FATIGUE": return "battery.25"
        case "HEADACHE": return "brain.head.profile"
        case "ANXIOUS": return "exclamationmark.triangle"
        case "INSOMNIA": return "moon.zzz"
        case "SINUS_PRESSURE": return "wind"
        case "LIGHT_SENSITIVITY": return "sun.max"
        case "JOINT_PAIN": return "figure.walk"
        case "PAIN": return "bandage"
        case "STIFFNESS": return "figure.walk.motion"
        case "BRAIN_FOG": return "cloud.fog"
        case "RESP_IRRITATION": return "wind"
        case "CHEST_TIGHTNESS": return "heart"
        case "PALPITATIONS": return "heart.fill"
        case "WIRED": return "bolt.fill"
        case "RESTLESS_SLEEP": return "bed.double"
        default: return "ellipsis"
        }
    }

    static func fromDefinitions(_ definitions: [SymptomCodeDefinition]) -> [SymptomPreset] {
        var seen: Set<String> = []
        let mapped = definitions.filter { $0.isActive }.compactMap { definition -> SymptomPreset? in
            let preset = SymptomPreset(definition: definition)
            if seen.insert(preset.code).inserted {
                return preset
            }
            return nil
        }
        return ensureFallback(in: mapped)
    }

    static func ensureFallback(in presets: [SymptomPreset]) -> [SymptomPreset] {
        var filtered = presets.filter { $0.code != SymptomCodeHelper.fallbackCode }
        if let existing = presets.first(where: { $0.code == SymptomCodeHelper.fallbackCode }) {
            filtered.append(existing)
        } else {
            filtered.append(SymptomPreset(code: SymptomCodeHelper.fallbackCode, label: "Other", systemImage: "ellipsis"))
        }
        return filtered
    }

    static let defaults: [SymptomPreset] = ensureFallback(in: [
        SymptomPreset(code: "NERVE_PAIN", label: "Nerve pain", systemImage: "bolt.heart"),
        SymptomPreset(code: "ZAPS", label: "Zaps", systemImage: "bolt"),
        SymptomPreset(code: "NAUSEA", label: "Nausea", systemImage: "mouth"),
        SymptomPreset(code: "BLOATING", label: "Bloating", systemImage: "circle.dotted"),
        SymptomPreset(code: "STOMACH_PAIN", label: "Stomach pain", systemImage: "cross.case"),
        SymptomPreset(code: "REFLUX", label: "Reflux", systemImage: "flame"),
        SymptomPreset(code: "DIGESTIVE_UPSET", label: "Digestive upset", systemImage: "cross.case.fill"),
        SymptomPreset(code: "BOWEL_URGENCY", label: "Bowel urgency", systemImage: "figure.walk.motion"),
        SymptomPreset(code: "DRAINED", label: "Drained", systemImage: "battery.25"),
        SymptomPreset(code: "FATIGUE", label: "Fatigue", systemImage: "battery.25"),
        SymptomPreset(code: "HEADACHE", label: "Headache", systemImage: "brain.head.profile"),
        SymptomPreset(code: "ANXIOUS", label: "Anxious", systemImage: "exclamationmark.triangle"),
        SymptomPreset(code: "INSOMNIA", label: "Insomnia", systemImage: "moon.zzz"),
        SymptomPreset(code: "SINUS_PRESSURE", label: "Sinus pressure", systemImage: "wind"),
        SymptomPreset(code: "LIGHT_SENSITIVITY", label: "Light sensitivity", systemImage: "sun.max"),
        SymptomPreset(code: "JOINT_PAIN", label: "Joint pain", systemImage: "figure.walk"),
        SymptomPreset(code: "PAIN", label: "Pain flare", systemImage: "bandage"),
        SymptomPreset(code: "STIFFNESS", label: "Stiffness", systemImage: "figure.walk.motion"),
        SymptomPreset(code: "BRAIN_FOG", label: "Brain fog", systemImage: "cloud.fog"),
        SymptomPreset(code: "RESP_IRRITATION", label: "Breathing irritation", systemImage: "wind"),
        SymptomPreset(code: "CHEST_TIGHTNESS", label: "Chest tightness", systemImage: "heart"),
        SymptomPreset(code: "PALPITATIONS", label: "Palpitations", systemImage: "heart.fill"),
        SymptomPreset(code: "WIRED", label: "Wired", systemImage: "bolt.fill"),
        SymptomPreset(code: "RESTLESS_SLEEP", label: "Restless sleep", systemImage: "bed.double"),
        SymptomPreset(code: "OTHER", label: "Other", systemImage: "ellipsis"),
    ])
}

struct SymptomItem: Identifiable, Hashable {
    let id: String
    let label: String
    let category: SymptomCategory
    let tags: [String]
}

enum SymptomCategory: String, CaseIterable, Identifiable {
    case head = "Head / Sensory"
    case pain = "Pain"
    case digestive = "Digestive / GI"
    case energy = "Energy"
    case sleep = "Sleep"
    case autonomic = "Heart / Nervous System"
    case other = "Other"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .head: return "brain.head.profile"
        case .pain: return "waveform.path.ecg"
        case .digestive: return "cross.case.fill"
        case .energy: return "bolt.heart"
        case .sleep: return "moon.stars.fill"
        case .autonomic: return "heart.text.square.fill"
        case .other: return "ellipsis.circle"
        }
    }
}

struct SymptomSuggestionContext {
    let activeDriverKeys: [String]
    let activePatternDriverKeys: [String]
    let activePatternOutcomeKeys: [String]
    let recentSymptomCodes: [String]
    let prefillTags: [String]
    let prefillSymptomCode: String?

    static let empty = SymptomSuggestionContext(
        activeDriverKeys: [],
        activePatternDriverKeys: [],
        activePatternOutcomeKeys: [],
        recentSymptomCodes: [],
        prefillTags: [],
        prefillSymptomCode: nil
    )
}

private enum SymptomCatalog {
    private static let categoryMap: [String: SymptomCategory] = [
        "HEADACHE": .head,
        "SINUS_PRESSURE": .head,
        "LIGHT_SENSITIVITY": .head,
        "BRAIN_FOG": .head,
        "PAIN": .pain,
        "NERVE_PAIN": .pain,
        "JOINT_PAIN": .pain,
        "STIFFNESS": .pain,
        "ZAPS": .pain,
        "NAUSEA": .digestive,
        "BLOATING": .digestive,
        "STOMACH_PAIN": .digestive,
        "REFLUX": .digestive,
        "DIGESTIVE_UPSET": .digestive,
        "BOWEL_URGENCY": .digestive,
        "FATIGUE": .energy,
        "DRAINED": .energy,
        "WIRED": .energy,
        "INSOMNIA": .sleep,
        "RESTLESS_SLEEP": .sleep,
        "PALPITATIONS": .autonomic,
        "CHEST_TIGHTNESS": .autonomic,
        "RESP_IRRITATION": .autonomic,
        "ANXIOUS": .autonomic,
        "OTHER": .other,
    ]

    private static let sortOrder: [String: Int] = [
        "HEADACHE": 0,
        "SINUS_PRESSURE": 1,
        "LIGHT_SENSITIVITY": 2,
        "BRAIN_FOG": 3,
        "PAIN": 10,
        "NERVE_PAIN": 11,
        "JOINT_PAIN": 12,
        "STIFFNESS": 13,
        "ZAPS": 14,
        "NAUSEA": 20,
        "BLOATING": 21,
        "STOMACH_PAIN": 22,
        "REFLUX": 23,
        "DIGESTIVE_UPSET": 24,
        "BOWEL_URGENCY": 25,
        "FATIGUE": 30,
        "DRAINED": 31,
        "WIRED": 32,
        "INSOMNIA": 40,
        "RESTLESS_SLEEP": 41,
        "PALPITATIONS": 50,
        "CHEST_TIGHTNESS": 51,
        "RESP_IRRITATION": 52,
        "ANXIOUS": 53,
        "OTHER": 60,
    ]

    static func item(from preset: SymptomPreset) -> SymptomItem {
        let code = normalize(preset.code)
        let trimmedLabel = preset.label.trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedLabel: String
        switch code {
        case "OTHER":
            resolvedLabel = "Other / Custom"
        case "RESP_IRRITATION":
            resolvedLabel = trimmedLabel.isEmpty ? "Breathing irritation" : trimmedLabel
        case "PAIN":
            resolvedLabel = trimmedLabel.isEmpty ? "Pain flare" : trimmedLabel
        default:
            resolvedLabel = trimmedLabel.isEmpty
                ? code.replacingOccurrences(of: "_", with: " ").capitalized
                : trimmedLabel
        }

        return SymptomItem(
            id: code,
            label: resolvedLabel,
            category: categoryMap[code] ?? .other,
            tags: preset.tags ?? []
        )
    }

    static func sortedItems(from presets: [SymptomPreset]) -> [SymptomItem] {
        presets
            .map(item(from:))
            .sorted { lhs, rhs in
                if lhs.category != rhs.category {
                    let lhsIndex = SymptomCategory.allCases.firstIndex(of: lhs.category) ?? Int.max
                    let rhsIndex = SymptomCategory.allCases.firstIndex(of: rhs.category) ?? Int.max
                    return lhsIndex < rhsIndex
                }
                let lhsRank = sortOrder[lhs.id] ?? Int.max
                let rhsRank = sortOrder[rhs.id] ?? Int.max
                if lhsRank != rhsRank {
                    return lhsRank < rhsRank
                }
                return lhs.label.localizedCaseInsensitiveCompare(rhs.label) == .orderedAscending
            }
    }
}

private enum SymptomSuggestionEngine {
    static func suggestions(items: [SymptomItem], context: SymptomSuggestionContext) -> [SymptomItem] {
        let lookup = Dictionary(uniqueKeysWithValues: items.map { ($0.id, $0) })
        var seen: Set<String> = []
        var ordered: [SymptomItem] = []

        func append(_ codes: [String]) {
            for raw in codes {
                let code = normalize(raw)
                guard let item = lookup[code], seen.insert(code).inserted else { continue }
                ordered.append(item)
            }
        }

        let driverKeys = Set(
            (context.activeDriverKeys + context.activePatternDriverKeys + context.prefillTags.compactMap(contextKey(from:)))
                .map(normalize)
        )

        for key in driverKeys {
            switch key {
            case "PRESSURE":
                append(["HEADACHE", "SINUS_PRESSURE", "LIGHT_SENSITIVITY"])
            case "AQI":
                append(["FATIGUE", "RESP_IRRITATION", "BRAIN_FOG"])
            case "ALLERGENS":
                append(["SINUS_PRESSURE", "HEADACHE", "BRAIN_FOG"])
            case "SCHUMANN":
                append(["ANXIOUS", "BRAIN_FOG", "RESTLESS_SLEEP"])
            case "KP", "BZ", "SW":
                append(["ANXIOUS", "BRAIN_FOG", "WIRED"])
            case "PAIN":
                append(["PAIN", "NERVE_PAIN", "STIFFNESS"])
            case "FOCUS":
                append(["BRAIN_FOG", "HEADACHE", "DRAINED"])
            case "ENERGY", "STAMINA":
                append(["FATIGUE", "DRAINED", "WIRED"])
            case "SLEEP":
                append(["RESTLESS_SLEEP", "INSOMNIA"])
            case "HEART":
                append(["PALPITATIONS", "CHEST_TIGHTNESS", "ANXIOUS"])
            case "MOOD":
                append(["ANXIOUS", "WIRED", "BRAIN_FOG"])
            case "HEALTH_STATUS":
                append(["DRAINED", "FATIGUE", "BRAIN_FOG"])
            case "TEMP":
                append(["PAIN", "STIFFNESS", "FATIGUE"])
            default:
                break
            }
        }

        for outcome in context.activePatternOutcomeKeys.map(normalize) {
            if outcome.contains("PAIN") {
                append(["PAIN", "NERVE_PAIN", "STIFFNESS"])
            }
            if outcome.contains("SLEEP") {
                append(["RESTLESS_SLEEP", "INSOMNIA"])
            }
            if outcome.contains("FOCUS") || outcome.contains("FOG") {
                append(["BRAIN_FOG", "DRAINED"])
            }
            if outcome.contains("ANXI") || outcome.contains("MOOD") {
                append(["ANXIOUS", "WIRED"])
            }
            if outcome.contains("FATIGUE") || outcome.contains("ENERGY") {
                append(["FATIGUE", "DRAINED"])
            }
        }

        if let prefillCode = context.prefillSymptomCode?.trimmingCharacters(in: .whitespacesAndNewlines),
           !prefillCode.isEmpty,
           normalize(prefillCode) != SymptomCodeHelper.fallbackCode {
            append([prefillCode])
        }

        append(Array(context.recentSymptomCodes.prefix(3)))
        return ordered
    }

    private static func contextKey(from tag: String) -> String? {
        let parts = tag.split(separator: ":", omittingEmptySubsequences: false)
        guard parts.count >= 3, parts[0].lowercased() == "context" else { return nil }
        return String(parts[2])
    }
}

private struct SymptomSectionCard<Content: View>: View {
    let title: String
    let icon: String
    let content: Content

    init(title: String, icon: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.icon = icon
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.headline)
                    .foregroundColor(.white.opacity(0.88))
                Text(title)
                    .font(.headline.weight(.semibold))
                Spacer()
            }
            content
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }
}

struct SymptomChip: View {
    let label: String
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(.subheadline.weight(.medium))
                .multilineTextAlignment(.leading)
                .foregroundColor(.white)
                .padding(.horizontal, 14)
                .padding(.vertical, 11)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(isSelected ? GaugePalette.elevated.opacity(0.26) : Color.white.opacity(0.05))
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(isSelected ? GaugePalette.elevated.opacity(0.68) : Color.white.opacity(0.09), lineWidth: 1)
                )
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

struct FlowChipGrid<Data: RandomAccessCollection, Content: View>: View where Data.Element: Identifiable {
    let items: Data
    @ViewBuilder let content: (Data.Element) -> Content

    private let columns = [GridItem(.adaptive(minimum: 132), spacing: 10)]

    var body: some View {
        LazyVGrid(columns: columns, alignment: .leading, spacing: 10) {
            ForEach(Array(items)) { item in
                content(item)
            }
        }
    }
}

struct SymptomsLogPage: View {
    @Environment(\.dismiss) private var dismiss

    let queuedCount: Int
    let isOffline: Bool
    @Binding var isSubmitting: Bool
    let showsCloseButton: Bool
    let onSubmit: ([SymptomQueuedEvent]) -> Void

    @State private var selectedSymptoms: Set<SymptomItem>
    @State private var severity: Double
    @State private var notes: String
    @State private var occurredAt: Date
    @State private var hiddenTags: [String]
    @State private var suggestedSymptoms: [SymptomItem]
    @FocusState private var notesFocused: Bool

    private let symptomItems: [SymptomItem]
    private let favoriteSymptoms: [SymptomItem]
    private let symptomsByCategory: [SymptomCategory: [SymptomItem]]

    init(
        presets: [SymptomPreset],
        queuedCount: Int,
        isOffline: Bool,
        isSubmitting: Binding<Bool>,
        prefill: SymptomQueuedEvent? = nil,
        suggestionContext: SymptomSuggestionContext = .empty,
        favoriteSymptomCodes: [String] = [],
        showsCloseButton: Bool = false,
        onSubmit: @escaping ([SymptomQueuedEvent]) -> Void
    ) {
        self.queuedCount = queuedCount
        self.isOffline = isOffline
        self._isSubmitting = isSubmitting
        self.showsCloseButton = showsCloseButton
        self.onSubmit = onSubmit

        let catalogItems = SymptomCatalog.sortedItems(from: presets)
        symptomItems = catalogItems
        let favoriteSet = Set(favoriteSymptomCodes.map(normalize))
        favoriteSymptoms = catalogItems.filter { favoriteSet.contains($0.id) && $0.id != SymptomCodeHelper.fallbackCode }

        var grouped: [SymptomCategory: [SymptomItem]] = [:]
        for item in catalogItems {
            if favoriteSet.contains(item.id) && item.id != SymptomCodeHelper.fallbackCode {
                continue
            }
            grouped[item.category, default: []].append(item)
        }
        symptomsByCategory = grouped

        let normalizedCode = prefill.map { normalize($0.symptomCode) }
        let hasPrefillNotes = !(prefill?.freeText?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "").isEmpty
        let initialSelection = normalizedCode.flatMap { code -> Set<SymptomItem>? in
            guard let item = catalogItems.first(where: { $0.id == code }) else { return nil }
            if code == SymptomCodeHelper.fallbackCode && !hasPrefillNotes {
                return nil
            }
            return [item]
        } ?? []

        _selectedSymptoms = State(initialValue: initialSelection)
        _severity = State(initialValue: Double(min(10, max(1, prefill?.severity ?? 5))))
        _notes = State(initialValue: prefill?.freeText ?? "")
        _occurredAt = State(initialValue: prefill?.tsUtc ?? Date())
        _hiddenTags = State(initialValue: prefill?.tags ?? [])
        _suggestedSymptoms = State(initialValue: SymptomSuggestionEngine.suggestions(items: catalogItems, context: suggestionContext))
    }

    private var selectedSymptomItems: [SymptomItem] {
        symptomItems.filter { selectedSymptoms.contains($0) }
    }

    private var trimmedNotes: String {
        notes.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var isSubmitDisabled: Bool {
        selectedSymptoms.isEmpty || isSubmitting
    }

    private var severityDescriptor: String {
        switch Int(severity) {
        case 1...2: return "Light"
        case 3...4: return "Mild"
        case 5...6: return "Moderate"
        case 7...8: return "Strong"
        default: return "Severe"
        }
    }

    private var saveButtonTitle: String {
        let count = selectedSymptoms.count
        guard count > 0 else { return "Save Symptoms" }
        return count == 1 ? "Save 1 Symptom" : "Save \(count) Symptoms"
    }

    private func toggleSelection(_ item: SymptomItem) {
        if selectedSymptoms.contains(item) {
            selectedSymptoms.remove(item)
        } else {
            selectedSymptoms.insert(item)
        }
    }

    private func mergedTags() -> [String]? {
        var seen: Set<String> = []
        var out: [String] = []
        for raw in hiddenTags + selectedSymptomItems.flatMap(\.tags) {
            let tag = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if tag.isEmpty || !seen.insert(tag).inserted {
                continue
            }
            out.append(tag)
        }
        return out.isEmpty ? nil : out
    }

    private func buildQueuedEvents() -> [SymptomQueuedEvent] {
        let timestamp = occurredAt
        let note = trimmedNotes.isEmpty ? nil : trimmedNotes
        let tags = mergedTags()
        let sharedSeverity = Int(severity)

        return selectedSymptomItems.map { item in
            SymptomQueuedEvent(
                symptomCode: item.id,
                tsUtc: timestamp,
                severity: sharedSeverity,
                freeText: note,
                tags: tags
            )
        }
    }

    private func submit() {
        let events = buildQueuedEvents()
        guard !events.isEmpty else { return }
        onSubmit(events)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if queuedCount > 0 {
                    Text("\(queuedCount) symptom(s) waiting to sync")
                        .font(.caption.weight(.medium))
                        .foregroundColor(.orange)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(Color.orange.opacity(0.12))
                        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }

                if isOffline {
                    Label("Offline right now. New symptom logs will queue and sync automatically.", systemImage: "wifi.slash")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                SymptomSectionCard(title: "When", icon: "calendar.badge.clock") {
                    DatePicker(
                        "Date & time",
                        selection: $occurredAt,
                        displayedComponents: [.date, .hourAndMinute]
                    )
                    .datePickerStyle(.compact)
                }

                if !suggestedSymptoms.isEmpty {
                    SymptomSectionCard(title: "Suggested right now", icon: "sparkles") {
                        Text("Suggestions use current drivers, active patterns, recent logs, and any modal context.")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        FlowChipGrid(items: suggestedSymptoms) { item in
                            SymptomChip(
                                label: item.label,
                                isSelected: selectedSymptoms.contains(item)
                            ) {
                                toggleSelection(item)
                            }
                        }
                    }
                }

                if !selectedSymptomItems.isEmpty {
                    SymptomSectionCard(title: "Selected symptoms", icon: "checkmark.circle.fill") {
                        Text("Tap a selected chip to remove it before saving.")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        FlowChipGrid(items: selectedSymptomItems) { item in
                            SymptomChip(label: item.label, isSelected: true) {
                                selectedSymptoms.remove(item)
                            }
                        }
                    }
                }

                if !favoriteSymptoms.isEmpty {
                    SymptomSectionCard(title: "Favorites", icon: "star.fill") {
                        Text("These stay at the top because you marked them as go-to symptoms in Settings.")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        FlowChipGrid(items: favoriteSymptoms) { item in
                            SymptomChip(
                                label: item.label,
                                isSelected: selectedSymptoms.contains(item)
                            ) {
                                toggleSelection(item)
                            }
                        }
                    }
                }

                ForEach(SymptomCategory.allCases) { category in
                    if let items = symptomsByCategory[category], !items.isEmpty {
                        SymptomSectionCard(title: category.rawValue, icon: category.icon) {
                            FlowChipGrid(items: items) { item in
                                SymptomChip(
                                    label: item.label,
                                    isSelected: selectedSymptoms.contains(item)
                                ) {
                                    toggleSelection(item)
                                }
                            }
                        }
                    }
                }

                SymptomSectionCard(title: "Severity", icon: "dial.medium") {
                    VStack(alignment: .leading, spacing: 10) {
                        Slider(value: $severity, in: 1...10, step: 1)

                        HStack {
                            Text("Intensity: \(Int(severity))/10")
                                .font(.subheadline.weight(.semibold))
                            Spacer()
                            Text(severityDescriptor)
                                .font(.caption.weight(.semibold))
                                .foregroundColor(GaugePalette.elevated)
                        }
                        .foregroundColor(.secondary)
                    }
                }

                SymptomSectionCard(title: "Notes (optional)", icon: "note.text") {
                    TextField("Anything else you want to note?", text: $notes, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                        .lineLimit(3...6)
                        .focused($notesFocused)
                }

                Button(action: submit) {
                    Text(saveButtonTitle)
                        .font(.headline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(GaugePalette.elevated)
                .disabled(isSubmitDisabled)
            }
            .padding()
        }
        .navigationTitle("Log Symptoms")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if showsCloseButton {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") {
                    submit()
                }
                .disabled(isSubmitDisabled)
            }
        }
        .interactiveDismissDisabled(isSubmitting)
        .onDisappear {
            notesFocused = false
        }
    }
}
