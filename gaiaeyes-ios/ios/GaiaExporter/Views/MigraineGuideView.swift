import SwiftUI

struct MigraineGuideView: View {
    @StateObject private var store: MigraineGuideStore
    @Environment(\.dismiss) private var dismiss
    @State private var proposedStart = Date()
    @State private var customChoice = ""
    @State private var favoritesRevision = 0
    @State private var showSavedSummary = false
    @State private var confirmDiscard = false
    let onSaved: (String) -> Void

    init(api: APIClient, episodeID: String? = nil, accountScope: @escaping @MainActor () -> String,
         onSaved: @escaping (String) -> Void) {
        _store = StateObject(wrappedValue: MigraineGuideStore(api: api, episodeID: episodeID, accountScope: accountScope))
        self.onSaved = onSaved
    }
    private var step: MigraineGuideStep { store.draft.step }
    private var index: Int { MigraineGuideStep.allCases.firstIndex(of: step) ?? 0 }
    private func field<T>(_ key: WritableKeyPath<MigraineGuideDraft, T>, changed: String? = nil) -> Binding<T> {
        Binding(get: { store.draft[keyPath: key] }, set: { value in
            guard !store.locked else { return }
            store.draft[keyPath: key] = value
            if let changed { store.draft.changed.insert(changed) }
        })
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Step \(index + 1) of \(MigraineGuideStep.allCases.count)").font(.caption).foregroundStyle(.secondary)
                        Label(step.title, systemImage: step.symbol).font(.title2.bold())
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    ProgressView(value: Double(index + 1), total: Double(MigraineGuideStep.allCases.count))
                        .accessibilityLabel("Migraine details, step \(index + 1) of \(MigraineGuideStep.allCases.count)")
                    if !store.sameAccount {
                        Text(MigraineDraftError.accountChanged.localizedDescription).foregroundStyle(.orange)
                    } else if !store.ready {
                        if store.busy { ProgressView("Loading saved migraine…") }
                        else { Button("Retry loading") { Task { await store.load() } } }
                    } else {
                        stepContent.disabled(store.locked)
                        if store.draft.inputsLocked {
                            Text("These answers are kept for the same save attempt.").font(.footnote)
                            Button("Retry same save") { save() }.disabled(store.busy)
                                .accessibilityIdentifier("migraine-guide-retry")
                            if store.draft.episodeID != nil {
                                Button("Review saved summary") { showSavedSummary = true }
                                Button("Discard this draft and load saved version", role: .destructive) { confirmDiscard = true }
                            }
                        }
                    }
                    if let message = store.message {
                        Text(message).foregroundStyle(message == "Saved" ? Color.secondary : Color.orange)
                            .accessibilityIdentifier("migraine-guide-message")
                    }
                    if store.draft.episodeID == nil {
                        Text("Your start time is required to save an episode. Every other detail is optional. You can close and resume this draft.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Color(red: 0.03, green: 0.05, blue: 0.09)).foregroundStyle(.white).tint(.cyan)
            .navigationTitle(store.draft.episodeID == nil ? "Log migraine" : "Migraine details")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { store.persist(); dismiss() }.disabled(store.busy)
                }
                ToolbarItem(placement: .primaryAction) {
                    Button(store.busy ? "Saving…" : "Save") { save() }
                        .disabled(store.busy || !store.ready || !store.sameAccount || store.draft.onset == nil)
                        .accessibilityLabel("Save and finish later")
                        .accessibilityIdentifier("migraine-guide-save")
                }
            }
            .safeAreaInset(edge: .bottom) {
                MigraineGuideNavigation(index: index, reviewing: step == .review,
                    saveTitle: store.draft.episodeID == nil ? "Save active migraine" : "Save changes",
                    canSave: store.draft.onset != nil, onBack: { move(-1) }, onNext: { move(1) }, onSave: save)
                    .padding().background(.ultraThinMaterial).disabled(store.busy || !store.ready || !store.sameAccount)
            }
#if DEBUG && GAIA_MIGRAINE_APP_VERIFICATION
            .transformEnvironment(\.dynamicTypeSize) { size in
                if MigraineAppVerification.isActive && MigraineAppVerification.largeText { size = .accessibility3 }
            }
#endif
            .task { await store.load() }
            .onChange(of: store.draft) { _, _ in store.persist() }
            .onDisappear { store.persist() }
            .interactiveDismissDisabled(store.busy)
            .confirmationDialog("Discard these unsaved details?", isPresented: $confirmDiscard, titleVisibility: .visible) {
                Button("Discard draft", role: .destructive) { Task { await store.discardAndReload() } }
            } message: { Text("Your saved episode will be kept. This removes only the changes in this draft.") }
            .sheet(isPresented: $showSavedSummary) {
                if let id = store.draft.episodeID {
                    MigraineEpisodeSummaryView(api: store.api, episodeID: id, accountScope: store.scope,
                        timeZone: .current, accountScopeProvider: store.accountScope)
                }
            }
        }
    }
    private func move(_ delta: Int) {
        let next = min(max(0, index + delta), MigraineGuideStep.allCases.count - 1)
        store.draft.step = MigraineGuideStep.allCases[next]; customChoice = ""; store.persist()
    }
    private func save() {
        Task { if let id = await store.save() { onSaved(id); dismiss() } }
    }
    @ViewBuilder private var stepContent: some View {
        switch step {
        case .timing:
            if let onset = store.draft.onset {
                Label("Started \(onset.formatted(date: .abbreviated, time: .shortened))", systemImage: "clock")
                    .accessibilityIdentifier("migraine-guide-start-confirmed")
            } else { Text("No start time selected").foregroundStyle(.secondary) }
            if store.draft.episodeID == nil {
                Button("Started now") { store.draft.onset = Date() }.buttonStyle(.borderedProminent)
                    .accessibilityIdentifier("migraine-guide-start-now")
                Text("Choose a start time").fixedSize(horizontal: false, vertical: true)
                DatePicker("Choose a start time", selection: $proposedStart, in: ...Date(), displayedComponents: [.date, .hourAndMinute])
                    .labelsHidden()
                Button("Use selected start time") { store.draft.onset = proposedStart }
                Text("The picker is a suggestion until you choose Use selected start time.").font(.footnote).foregroundStyle(.secondary)
            } else {
                Text("The saved start is kept. Use Edit times in the episode summary to correct it.").font(.footnote)
                Button("Open saved summary") { showSavedSummary = true }
            }
            Label("Stays active until you choose End migraine", systemImage: "checkmark.circle")
        case .severity:
            if let previous = store.draft.base?.episode.severity {
                Text("Last reported: \(previous)/10. Choose a value only if you want to report it now.").font(.footnote)
            }
            MigraineSeverityScale(value: Binding(get: { store.draft.severity }, set: {
                store.draft.severity = $0; store.draft.severityChanged = $0 != nil
            }))
            Text("This is your current severity. It does not replace your earlier reports or end the migraine.").font(.footnote).foregroundStyle(.secondary)
        case .symptoms:
            choices(category: "symptoms", defaults: step.choices, selection: field(\.symptoms, changed: "symptoms"))
            Text("Early signs before the migraine (optional)").font(.headline)
            choices(category: "earlySigns", defaults: ["Visual changes", "Yawning", "Neck stiffness"], selection: field(\.earlySigns, changed: "earlySigns"), custom: false)
        case .location:
            Label("Use your left and right", systemImage: "person.crop.square").font(.headline)
            choices(category: "location", defaults: step.choices, selection: field(\.locations, changed: "location"))
        case .medicines:
            medicineFields
        case .relief:
            Text("Record something you tried. These choices are not treatment recommendations.").font(.footnote).foregroundStyle(.secondary)
            choices(category: "relief", defaults: step.choices, selection: field(\.reliefs, changed: "relief"))
        case .context:
            Text("Optional observations around the migraine. They do not establish its cause.").font(.footnote).foregroundStyle(.secondary)
            choices(category: "context", defaults: step.choices, selection: field(\.contexts, changed: "context"))
            Text("Notes").font(.headline)
            TextField("Anything you want to remember", text: field(\.notes, changed: "notes"), axis: .vertical)
                .lineLimit(3...8).textFieldStyle(.roundedBorder).accessibilityIdentifier("migraine-guide-notes")
        case .review:
            review
        }
    }
    private func choices(category: String, defaults: [String], selection: Binding<[String]>, custom: Bool = true) -> some View {
        let pinned = MigraineGuideStorage.favorites(scope: store.scope, category: category)
        let labels = (pinned + defaults + selection.wrappedValue).reduce(into: [String]()) { if !$0.contains($1) { $0.append($1) } }
        return VStack(alignment: .leading, spacing: 10) {
            Text("Star a choice to keep it handy. Favorites are never selected automatically.").font(.caption).foregroundStyle(.secondary)
            ForEach(labels, id: \.self) { label in
                HStack {
                    Button {
                        if selection.wrappedValue.contains(label) { selection.wrappedValue.removeAll { $0 == label } }
                        else { selection.wrappedValue.append(label) }
                    } label: {
                        Label(label, systemImage: selection.wrappedValue.contains(label) ? "checkmark.circle.fill" : "circle")
                            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    }.accessibilityValue(selection.wrappedValue.contains(label) ? "Selected" : "Not selected")
                    Button {
                        MigraineGuideStorage.toggleFavorite(label, scope: store.scope, category: category); favoritesRevision += 1
                    } label: { Image(systemName: pinned.contains(label) ? "star.fill" : "star").frame(width: 44, height: 44) }
                        .accessibilityLabel("\(pinned.contains(label) ? "Remove" : "Save") favorite: \(label)")
                }.padding(.horizontal, 12).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
            }
            if custom {
                TextField("Add your own", text: $customChoice).textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("migraine-guide-custom")
                Button("Add choice") {
                    let label = customChoice.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !label.isEmpty && !selection.wrappedValue.contains(label) { selection.wrappedValue.append(label) }
                    customChoice = ""
                }.disabled(customChoice.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || customChoice.count > 160)
            }
        }.id("\(category)-\(favoritesRevision)")
    }
    @ViewBuilder private var medicineFields: some View {
        let favorites = MigraineGuideStorage.favorites(scope: store.scope, category: "medicines")
        Text("A medicine is recorded only after you choose its name and taken time and save. Dose and relief are optional.")
            .font(.footnote).foregroundStyle(.secondary)
        ForEach(favorites, id: \.self) { name in
            Button("Use favorite: \(name)") {
                var medicine = MigraineGuideMedicine(); medicine.name = name
                store.draft.medicines.append(medicine); store.draft.changed.insert("medicines")
            }
        }
        if store.draft.medicines.isEmpty { Text("No medicine entries recorded").foregroundStyle(.secondary) }
        ForEach(store.draft.medicines) { row in
            MigraineGuideMedicineFields(medicine: Binding(get: { store.draft.medicines.first(where: { $0.id == row.id }) ?? row }, set: { value in
                guard let index = store.draft.medicines.firstIndex(where: { $0.id == row.id }) else { return }
                store.draft.medicines[index] = value; store.draft.changed.insert("medicines")
            }), isFavorite: favorites.contains(row.name.trimmingCharacters(in: .whitespacesAndNewlines)), onFavorite: { name in
                MigraineGuideStorage.toggleFavorite(name, scope: store.scope, category: "medicines"); favoritesRevision += 1
            }, onRemove: {
                store.draft.medicines.removeAll { $0.id == row.id }; store.draft.changed.insert("medicines")
            })
        }
        Button { store.draft.medicines.append(MigraineGuideMedicine()); store.draft.changed.insert("medicines") }
            label: { Label("Add medicine", systemImage: "plus.circle") }
            .accessibilityIdentifier("migraine-guide-add-medicine")
    }
    private var review: some View {
        VStack(alignment: .leading, spacing: 14) {
            Label(store.draft.base?.episode.state == "resolved" ? "Ended migraine" : "Migraine active", systemImage: "waveform.path")
                .font(.headline)
            reviewRow("Start", store.draft.onset?.formatted(date: .abbreviated, time: .shortened) ?? "Choose a start time", step: .timing)
            reviewRow("Current severity", store.draft.severity.map { "\($0)/10, reporting now" }
                ?? store.draft.base?.episode.severity.map { "Last reported: \($0)/10; unchanged" } ?? "Not reported", step: .severity)
            reviewRow("Symptoms", joined(store.draft.symptoms), step: .symptoms)
            reviewRow("Pain location", joined(store.draft.locations), step: .location)
            reviewRow("Medicines", store.draft.medicines.isEmpty ? "None recorded" : store.draft.medicines.map { $0.name.isEmpty ? "Unfinished entry" : $0.name }.joined(separator: ", "), step: .medicines)
            reviewRow("Other relief", joined(store.draft.reliefs), step: .relief)
            reviewRow("Context and notes", joined(store.draft.contexts) + (store.draft.notes.isEmpty ? "" : "\n" + store.draft.notes), step: .context)
        }
    }
    private func joined(_ values: [String]) -> String { values.isEmpty ? "Not recorded" : values.joined(separator: ", ") }
    private func reviewRow(_ title: String, _ value: String, step: MigraineGuideStep) -> some View {
        Button { store.draft.step = step } label: {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 5) { Text(title).font(.headline); Text(value).foregroundStyle(.secondary) }
                Spacer(); Image(systemName: "pencil")
            }.padding(14).frame(maxWidth: .infinity, alignment: .leading)
                .background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
        }.buttonStyle(.plain).accessibilityHint("Edit \(title.lowercased())")
    }
}

private struct MigraineGuideNavigation: View {
    @Environment(\.dynamicTypeSize) private var typeSize
    let index: Int
    let reviewing: Bool
    let saveTitle: String
    let canSave: Bool
    var onBack: () -> Void
    var onNext: () -> Void
    var onSave: () -> Void
    var body: some View {
        VStack(spacing: 12) {
            if typeSize.isAccessibilitySize {
                HStack {
                    if index > 0 { back }
                    Spacer(minLength: 8)
                    if !reviewing { skip }
                }
                primary.frame(maxWidth: .infinity)
            } else {
                HStack(spacing: 16) {
                    if index > 0 { back }
                    Spacer(minLength: 8)
                    if !reviewing { skip }
                    primary
                }
            }
        }
    }
    private var back: some View { Button("Back", action:onBack).buttonStyle(.bordered).fixedSize() }
    private var skip: some View {
        Button("Skip for now", action:onNext).fixedSize(horizontal:true,vertical:false)
            .accessibilityIdentifier("migraine-guide-skip")
    }
    @ViewBuilder private var primary: some View {
        if reviewing {
            Button(saveTitle, action:onSave).buttonStyle(.borderedProminent).disabled(!canSave)
                .fixedSize(horizontal:false,vertical:true).accessibilityIdentifier("migraine-guide-confirm")
        } else {
            Button("Next", action:onNext).buttonStyle(.borderedProminent).fixedSize()
                .accessibilityIdentifier("migraine-guide-next")
        }
    }
}

struct MigraineSeverityScale: View {
    @Environment(\.dynamicTypeSize) private var typeSize
    @Binding var value: Int?
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(value.map { "\($0) / 10" } ?? "Not selected").font(.largeTitle.bold())
                .accessibilityIdentifier("migraine-severity-value")
            LazyVGrid(columns: [GridItem(.adaptive(minimum: typeSize.isAccessibilitySize ? 80 : 52))], spacing: 10) {
                ForEach(0...10, id: \.self) { number in
                    Button { value = number } label: {
                        Text("\(number)").font(.headline).frame(maxWidth: .infinity, minHeight: 48)
                            .background(value == number ? Color.cyan.opacity(0.3) : .white.opacity(0.07), in: RoundedRectangle(cornerRadius: 10))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(value == number ? Color.cyan : .clear, lineWidth: 2))
                    }.accessibilityLabel("Severity \(number) out of 10")
                        .accessibilityValue(value == number ? "Selected" : "Not selected")
                        .accessibilityIdentifier("migraine-severity-\(number)")
                }
            }
            Text("0 · No pain     10 · Worst pain you can imagine").font(.footnote)
            if let selected = value {
                Slider(value: Binding(get: { Double(value ?? selected) }, set: { value = Int($0) }), in: 0...10, step: 1)
                    .accessibilityLabel("Current severity").accessibilityValue("\(selected) out of 10")
            }
            Button("Leave unanswered") { value = nil }.font(.footnote)
        }.buttonStyle(.plain)
    }
}

private struct MigraineGuideMedicineFields: View {
    @Binding var medicine: MigraineGuideMedicine
    var isFavorite: Bool
    var onFavorite: (String) -> Void
    var onRemove: () -> Void
    @State private var proposedTime = Date()
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(medicine.name.isEmpty ? "New medicine" : medicine.name).font(.headline)
            TextField("Medicine name", text: $medicine.name).textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("migraine-guide-medicine-name")
            if let taken = medicine.takenAt { Text("Taken: \(taken.formatted(date: .abbreviated, time: .shortened))") }
            else { Text("Taken time not selected").foregroundStyle(.secondary) }
            Button("Taken now") { medicine.takenAt = Date() }.accessibilityIdentifier("migraine-guide-medicine-now")
            Text("Choose taken time").fixedSize(horizontal: false, vertical: true)
            DatePicker("Choose taken time", selection: $proposedTime, in: ...Date(), displayedComponents: [.date, .hourAndMinute])
                .labelsHidden()
            Button("Use selected taken time") { medicine.takenAt = proposedTime }
            Text("Dose amount (optional)").font(.subheadline)
            TextField("Dose amount (optional)", text: $medicine.dose).keyboardType(.decimalPad).textFieldStyle(.roundedBorder)
            Text("Dose unit (if amount entered)").font(.subheadline)
            TextField("Dose unit (if amount entered)", text: $medicine.unit).textFieldStyle(.roundedBorder)
            Text("Reported relief (optional)").font(.subheadline)
            Picker("Reported relief (optional)", selection: $medicine.relief) {
                ForEach(MigraineReliefChoice.allCases) { choice in Text(choice.label).tag(choice.rawValue) }
            }
            Text("Medicine note (optional)").font(.subheadline)
            TextField("Medicine note (optional)", text: $medicine.notes, axis: .vertical).textFieldStyle(.roundedBorder)
            Button(isFavorite ? "Remove medicine favorite" : "Save medicine favorite") { onFavorite(medicine.name.trimmingCharacters(in: .whitespacesAndNewlines)) }
                .disabled(medicine.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            Button("Remove entry", role: .destructive, action: onRemove)
        }.padding(16).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 16))
    }
}
