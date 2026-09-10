import SwiftUI

struct MigraineTimeFields: View {
    @ObservedObject var store: MigraineTimeEditorStore
    var onSave: @MainActor () async -> Void
    @FocusState private var focusedField: String?

    private func binding<T>(_ key: WritableKeyPath<MigraineTimeDraft, T>, fallback: T) -> Binding<T> {
        Binding(get: { store.draft?[keyPath: key] ?? fallback }, set: { value in store.edit { $0[keyPath: key] = value } })
    }
    private func wallBinding(_ end: Bool, _ key: WritableKeyPath<MigraineWallTime, String>) -> Binding<String> {
        Binding(get: { (end ? store.draft?.end : store.draft?.start)?[keyPath: key] ?? "" }, set: { value in
            store.edit { draft in
                if end { draft.end[keyPath: key] = value; draft.end.offsetChoice = nil }
                else { draft.start[keyPath: key] = value; draft.start.offsetChoice = nil }
            }
        })
    }
    private func storedTime(_ timestamp: MigraineEpisodeTimestamp?) -> String {
        guard let timestamp else { return "End unknown" }
        let wall = MigraineWallTime(timestamp: timestamp)
        return "\(wall.dateText) at \(wall.timeText) · \(wall.zoneName)"
    }
    @ViewBuilder private func fields(end: Bool) -> some View {
        let prefix = end ? "migraine-time-end" : "migraine-time-start"
        VStack(alignment: .leading, spacing: 4) {
            Text(end ? "End date" : "Start date").font(.caption).foregroundStyle(.secondary)
            TextField("Date (YYYY-MM-DD)", text: wallBinding(end, \.dateText))
                .accessibilityLabel(end ? "End date" : "Start date")
                .accessibilityIdentifier(prefix + "-date").focused($focusedField, equals: prefix + "-date")
        }
        VStack(alignment: .leading, spacing: 4) {
            Text(end ? "End time (24-hour)" : "Start time (24-hour)").font(.caption).foregroundStyle(.secondary)
            TextField("Time (24-hour HH:mm)", text: wallBinding(end, \.timeText))
                .accessibilityLabel(end ? "End time, 24-hour" : "Start time, 24-hour")
                .accessibilityIdentifier(prefix + "-clock").focused($focusedField, equals: prefix + "-clock")
        }
        VStack(alignment: .leading, spacing: 4) {
            Text(end ? "End timezone" : "Start timezone").font(.caption).foregroundStyle(.secondary)
            TextField("Timezone (e.g. America/Chicago)", text: wallBinding(end, \.zoneName))
                .accessibilityLabel(end ? "End timezone" : "Start timezone")
                .accessibilityIdentifier(prefix + "-zone").focused($focusedField, equals: prefix + "-zone")
                .textInputAutocapitalization(.never).autocorrectionDisabled()
        }
        let wall = end ? store.draft?.end : store.draft?.start
        if let options = try? wall?.candidates(), options.count > 1 {
            Picker("Repeated local time", selection: Binding<Int?>(get: { wall?.offsetChoice }, set: { offset in
                store.edit { if end { $0.end.offsetChoice = offset } else { $0.start.offsetChoice = offset } }
            })) {
                Text("Choose occurrence").tag(Int?.none)
                ForEach(Array(options.enumerated()), id: \.offset) { index, time in
                    Text("\(index == 0 ? "First" : "Second") (UTC offset \(time.utcOffsetMinutes ?? 0) min)")
                        .tag(time.utcOffsetMinutes)
                }
            }.accessibilityIdentifier(prefix + "-occurrence")
        }
    }
    var body: some View {
        Section("Migraine times") {
            if let context = store.context, let draft = store.draft {
                Text("Saved start: " + storedTime(context.episode.start))
                    .accessibilityIdentifier("migraine-time-saved-start")
                Text("Saved end: " + storedTime(context.episode.end))
                    .accessibilityIdentifier("migraine-time-saved-end")
                if context.inconsistentEnd {
                    Text("The stored end is inconsistent with this episode. Correct the start or end, or explicitly mark the end unknown.")
                        .font(.footnote)
                }
                Toggle("Correct start", isOn: binding(\.correctStart, fallback: false))
                    .accessibilityIdentifier("migraine-time-start-mode")
                    .disabled(store.inputsLocked || store.pendingRequest != nil)
                if draft.correctStart {
                    fields(end: false).disabled(store.inputsLocked || store.pendingRequest != nil)
                }
                Picker("End correction", selection: binding(\.endMode, fallback: "retain")) {
                    Text("Keep saved end").tag("retain")
                    Text("Set end").tag("set")
                    Text("End unknown").tag("clear")
                }.accessibilityIdentifier("migraine-time-end-mode")
                    .disabled(store.inputsLocked || store.pendingRequest != nil)
                if draft.endMode == "set" {
                    fields(end: true).disabled(store.inputsLocked || store.pendingRequest != nil)
                }
                Picker("Episode status", selection: binding(\.state, fallback: "retain")) {
                    Text("Keep \(context.episode.state)").tag("retain")
                    ForEach(["new", "ongoing", "improving", "worse", "resolved"], id: \.self) { Text($0.capitalized).tag($0) }
                }.accessibilityIdentifier("migraine-time-state")
                    .disabled(store.inputsLocked || store.pendingRequest != nil)
                Text("An unknown end keeps the saved status. To reopen an ended episode, choose an active status and End unknown.")
                    .font(.footnote)
                Button(store.isSaving ? "Saving times…" : store.pendingRequest == nil ? "Save time correction" : "Retry same correction") {
                    focusedField = nil
                    Task { await onSave() }
                }.accessibilityIdentifier("migraine-time-save")
                    .disabled(store.inputsLocked || store.needsReload || (!draft.hasIntent && store.pendingRequest == nil))
            } else if store.isLoading {
                ProgressView("Loading saved times…")
            }
            if let message = store.message {
                Text(message).font(.footnote).accessibilityIdentifier("migraine-time-message")
            }
            if store.needsReload || store.pendingRequest != nil || store.context == nil {
                Button("Reload saved version") {
                    focusedField = nil
                    Task { await store.load(preservingDraft: true) }
                }.accessibilityIdentifier("migraine-time-reload").disabled(store.inputsLocked)
            }
        }
    }
}
