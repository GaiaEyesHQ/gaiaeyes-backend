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
        case "DRAINED": return "battery.25"
        case "HEADACHE": return "brain.head.profile"
        case "ANXIOUS": return "exclamationmark.triangle"
        case "INSOMNIA": return "moon.zzz"
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
        SymptomPreset(code: "DRAINED", label: "Drained", systemImage: "battery.25"),
        SymptomPreset(code: "HEADACHE", label: "Headache", systemImage: "brain.head.profile"),
        SymptomPreset(code: "ANXIOUS", label: "Anxious", systemImage: "exclamationmark.triangle"),
        SymptomPreset(code: "INSOMNIA", label: "Insomnia", systemImage: "moon.zzz"),
        SymptomPreset(code: "OTHER", label: "Other", systemImage: "ellipsis"),
    ])
}

struct SymptomsLogPage: View {
    @Environment(\.dismiss) private var dismiss

    let presets: [SymptomPreset]
    let queuedCount: Int
    let isOffline: Bool
    @Binding var isSubmitting: Bool
    let prefill: SymptomQueuedEvent?
    let showsCloseButton: Bool
    let onSubmit: (SymptomQueuedEvent) -> Void

    @State private var selectedPreset: SymptomPreset?
    @State private var includeSeverity: Bool
    @State private var severityValue: Double
    @State private var freeText: String
    @State private var occurredAt: Date
    @State private var hiddenTags: [String]
    @FocusState private var notesFocused: Bool

    init(
        presets: [SymptomPreset],
        queuedCount: Int,
        isOffline: Bool,
        isSubmitting: Binding<Bool>,
        prefill: SymptomQueuedEvent? = nil,
        showsCloseButton: Bool = false,
        onSubmit: @escaping (SymptomQueuedEvent) -> Void
    ) {
        self.presets = presets
        self.queuedCount = queuedCount
        self.isOffline = isOffline
        self._isSubmitting = isSubmitting
        self.prefill = prefill
        self.showsCloseButton = showsCloseButton
        self.onSubmit = onSubmit

        let normalizedCode = prefill.map { normalize($0.symptomCode) }
        let initialPreset = normalizedCode.flatMap { code in
            presets.first(where: { $0.code == code })
        }

        _selectedPreset = State(initialValue: initialPreset)
        _includeSeverity = State(initialValue: prefill?.severity != nil)
        _severityValue = State(initialValue: Double(prefill?.severity ?? 3))
        _freeText = State(initialValue: prefill?.freeText ?? "")
        _occurredAt = State(initialValue: prefill?.tsUtc ?? Date())
        _hiddenTags = State(initialValue: prefill?.tags ?? [])
    }

    private var trimmedFreeText: String {
        freeText.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var isSubmitDisabled: Bool {
        (selectedPreset == nil && trimmedFreeText.isEmpty) || isSubmitting
    }

    private func mergedTags() -> [String]? {
        var seen: Set<String> = []
        var out: [String] = []
        for raw in hiddenTags + (selectedPreset?.tags ?? []) {
            let tag = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if tag.isEmpty || !seen.insert(tag).inserted {
                continue
            }
            out.append(tag)
        }
        return out.isEmpty ? nil : out
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                if queuedCount > 0 {
                    Text("\(queuedCount) symptom(s) waiting to send")
                        .font(.caption)
                        .foregroundColor(.orange)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(8)
                        .background(Color.orange.opacity(0.1))
                        .cornerRadius(8)
                }

                if isOffline {
                    Label("Temporarily offline — showing last known symptoms.", systemImage: "wifi.slash")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                Text("Choose a symptom")
                    .font(.headline)

                DatePicker(
                    "When did this occur?",
                    selection: $occurredAt,
                    displayedComponents: [.date, .hourAndMinute]
                )
                .datePickerStyle(.compact)

                let columns = [GridItem(.adaptive(minimum: 110), spacing: 12)]
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(presets) { preset in
                        Button {
                            if selectedPreset == preset {
                                selectedPreset = nil
                                includeSeverity = false
                            } else {
                                selectedPreset = preset
                            }
                        } label: {
                            VStack(spacing: 8) {
                                Image(systemName: preset.systemImage)
                                    .font(.title2)
                                Text(preset.label)
                                    .font(.subheadline)
                            }
                            .frame(maxWidth: .infinity, minHeight: 70)
                        }
                        .buttonStyle(.bordered)
                        .tint(selectedPreset == preset ? .accentColor : .secondary)
                    }
                }

                if let preset = selectedPreset {
                    Divider()

                    VStack(alignment: .leading, spacing: 12) {
                        Text("Details for \(preset.label)")
                            .font(.headline)

                        Toggle("Include severity", isOn: $includeSeverity.animation())
                            .tint(.accentColor)

                        if includeSeverity {
                            VStack(alignment: .leading) {
                                Slider(value: $severityValue, in: 0...10, step: 1) {
                                    Text("Severity")
                                } minimumValueLabel: {
                                    Text("0")
                                } maximumValueLabel: {
                                    Text("10")
                                }
                                Text("Selected: \(Int(severityValue))")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }

                        TextField("Optional notes", text: $freeText, axis: .vertical)
                            .textFieldStyle(.roundedBorder)
                            .lineLimit(2...4)
                            .focused($notesFocused)
                    }
                }
            }
            .padding()
        }
        .navigationTitle("Log Symptom")
        .toolbar {
            if showsCloseButton {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
            ToolbarItem(placement: .confirmationAction) {
                Button("Save") {
                    let code = selectedPreset?.code ?? SymptomCodeHelper.fallbackCode
                    var event = SymptomQueuedEvent(symptomCode: code, tsUtc: occurredAt)
                    if includeSeverity { event.severity = Int(severityValue) }
                    if !trimmedFreeText.isEmpty { event.freeText = trimmedFreeText }
                    event.tags = mergedTags()
                    onSubmit(event)
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
