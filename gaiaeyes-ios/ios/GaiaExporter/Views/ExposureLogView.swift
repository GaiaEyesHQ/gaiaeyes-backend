import SwiftUI

struct ExposureLogView: View {
    let api: APIClient
    var source: String = "manual"
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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Log exposure")
                        .font(.title2.weight(.bold))
                    Text("Pick anything notable from today. Gaia Eyes watches for personal trigger patterns over time; this is not a diagnosis or certainty.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                LazyVGrid(columns: columns, spacing: 10) {
                    ForEach(ExposureOption.checkIn) { option in
                        exposureButton(option)
                    }
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
                    TextField("Optional context", text: $noteText, axis: .vertical)
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
