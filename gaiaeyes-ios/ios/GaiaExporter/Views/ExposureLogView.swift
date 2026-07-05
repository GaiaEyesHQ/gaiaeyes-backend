import SwiftUI

struct ExposureLogView: View {
    let api: APIClient
    var source: String = "manual"
    var focus: ExposureLogFocus = .general
    var showsCloseButton: Bool = true
    var onSaved: () -> Void = {}

    @Environment(\.dismiss) private var dismiss
    @State private var selected: Set<String> = []
    @State private var intensity: Int = 1
    @State private var noteText: String = ""
    @State private var isSaving: Bool = false
    @State private var statusMessage: String?
    @State private var alertMessage: String?

    private let columns = [GridItem(.flexible()), GridItem(.flexible())]

    private var headerTitle: String {
        switch focus {
        case .general:
            return "Log exposure"
        case .migraine:
            return "Log migraine triggers"
        }
    }

    private var headerBody: String {
        switch focus {
        case .general:
            return "Pick anything notable from today. Gaia Eyes will compare it with symptoms, wearables, and daily signals over time."
        case .migraine:
            return "Migraine days can have layered triggers. Pick anything that stood out, or use the note for your own context."
        }
    }

    private var primaryOptions: [ExposureOption] {
        focus == .migraine ? ExposureOption.migraineFocus : ExposureOption.checkIn
    }

    private var notePlaceholder: String {
        focus == .migraine ? "Other possible trigger, timing, aura, food, cycle, weather..." : "Optional context"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(headerTitle)
                        .font(.title2.weight(.bold))
                    Text(headerBody)
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                LazyVGrid(columns: columns, spacing: 10) {
                    ForEach(primaryOptions) { option in
                        exposureButton(option)
                    }
                }

                if focus == .migraine {
                    DisclosureGroup("More exposure categories") {
                        LazyVGrid(columns: columns, spacing: 10) {
                            ForEach(ExposureOption.checkIn.filter { option in
                                !ExposureOption.migraineFocus.contains(where: { $0.id == option.id })
                            }) { option in
                                exposureButton(option)
                            }
                        }
                        .padding(.top, 8)
                    }
                    .font(.subheadline.weight(.semibold))
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Intensity")
                        .font(.headline)
                    Picker("Intensity", selection: $intensity) {
                        Text("Light").tag(1)
                        Text("Noticeable").tag(2)
                        Text("Strong").tag(3)
                    }
                    .pickerStyle(.segmented)
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Note")
                        .font(.headline)
                    TextField(notePlaceholder, text: $noteText, axis: .vertical)
                        .lineLimit(2...4)
                        .textFieldStyle(.roundedBorder)
                }

                Button {
                    Task { await save() }
                } label: {
                    if isSaving {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                    } else {
                        Label("Save exposures", systemImage: "checkmark.circle.fill")
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(selected.isEmpty || isSaving)

                if let statusMessage {
                    Text(statusMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(16)
        }
        .navigationTitle("Exposure diary")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if showsCloseButton {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .alert("Exposure not saved", isPresented: Binding(
            get: { alertMessage != nil },
            set: { if !$0 { alertMessage = nil } }
        )) {
            Button("OK", role: .cancel) { alertMessage = nil }
        } message: {
            Text(alertMessage ?? "")
        }
    }

    private func exposureButton(_ option: ExposureOption) -> some View {
        let isSelected = selected.contains(option.id)
        return Button {
            if isSelected {
                selected.remove(option.id)
            } else {
                selected.insert(option.id)
            }
        } label: {
            Label(option.label, systemImage: option.systemImage)
                .font(.subheadline.weight(.semibold))
                .multilineTextAlignment(.leading)
                .lineLimit(3)
                .frame(maxWidth: .infinity, minHeight: 54, alignment: .leading)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
        }
        .buttonStyle(.plain)
        .foregroundStyle(isSelected ? .white : .primary)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(isSelected ? GaugePalette.low.opacity(0.85) : Color.secondary.opacity(0.12))
        )
    }

    private func save() async {
        guard !selected.isEmpty else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            for exposureKey in selected.sorted() {
                _ = try await api.postExposureEvent(
                    exposureKey: exposureKey,
                    intensity: intensity,
                    source: source,
                    noteText: noteText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : noteText
                )
            }
            statusMessage = "Saved \(selected.count) exposure\(selected.count == 1 ? "" : "s")."
            onSaved()
            dismiss()
        } catch {
            alertMessage = error.localizedDescription
        }
    }
}
