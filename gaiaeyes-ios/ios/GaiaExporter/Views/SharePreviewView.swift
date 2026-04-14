import Foundation
import SwiftUI

#if canImport(UIKit)
import UIKit
#endif

struct SharePreviewView: View {
    let draft: ShareDraft

    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var state: AppState
    @AppStorage("gaia.membership.cached_plan") private var cachedPlanRaw: String = MembershipPlan.free.rawValue
    @State private var selectedCaptionStyle: ShareCaptionStyle = .balanced
    @State private var editableCaption: String
    @State private var renderedImage: UIImage?
    @State private var isRendering: Bool = false
    @State private var renderError: String?
    @State private var showShareSheet: Bool = false
    @State private var hasTrackedOpen: Bool = false
    @State private var copyOverride: ShareCopyOverride?
    @State private var copyOverrideRequested: Bool = false

    init(draft: ShareDraft) {
        self.draft = draft
        _editableCaption = State(initialValue: draft.captions.text(for: .balanced))
    }

    private var plusUnlocked: Bool {
        let plan = MembershipPlan(rawValue: cachedPlanRaw) ?? .free
        return plan == .plus || plan == .pro
    }

    private var activeDraft: ShareDraft {
        draft.applying(copyOverride: copyOverride)
    }

    private var shareImageScope: ShareBackgroundResolver.CandidateScope {
        plusUnlocked ? .full : .basic
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.opacity(0.97).ignoresSafeArea()

                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        previewBlock
                        captionControls
                    }
                    .padding(16)
                }
            }
            .navigationTitle("Share Preview")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await renderPreview(force: true) }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(isRendering)
                }
            }
            .task {
                if !hasTrackedOpen {
                    hasTrackedOpen = true
                    AppAnalytics.track(
                        "share_opened",
                        properties: [
                            "share_type": draft.shareType.rawValue,
                            "surface": draft.surface,
                            "key": draft.analyticsKey ?? "unknown",
                        ]
                    )
                }
                await loadShareCopyOverrideIfNeeded()
                await renderPreview()
            }
            .onChange(of: selectedCaptionStyle, initial: false) { _, newValue in
                editableCaption = activeDraft.captions.text(for: newValue)
            }
            .sheet(isPresented: $showShareSheet) {
                if let renderedImage {
                    let draftForSheet = activeDraft
                    ShareSheetPresenter(
                        image: renderedImage,
                        text: editableCaption,
                        title: draftForSheet.card.title,
                        subtitle: draftForSheet.card.subtitle
                    ) { completed in
                        if completed {
                            ShareHistoryStore.recordCompletedShare(draft)
                            AppAnalytics.track(
                                "share_completed",
                                properties: [
                                    "share_type": draft.shareType.rawValue,
                                    "surface": draft.surface,
                                    "key": draft.analyticsKey ?? "unknown",
                                ]
                            )
                            dismiss()
                        } else {
                            AppAnalytics.track(
                                "share_canceled",
                                properties: [
                                    "share_type": draft.shareType.rawValue,
                                    "surface": draft.surface,
                                    "key": draft.analyticsKey ?? "unknown",
                                ]
                            )
                        }
                    }
                }
            }
        }
    }

    private var previewBlock: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Share", systemImage: "square.and.arrow.up")
                .font(.subheadline.weight(.semibold))
                .foregroundColor(.white.opacity(0.82))

            Group {
                if let renderedImage {
                    Image(uiImage: renderedImage)
                        .resizable()
                        .scaledToFit()
                        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 24, style: .continuous)
                                .stroke(Color.white.opacity(0.08), lineWidth: 1)
                        )
                } else if isRendering {
                    RoundedRectangle(cornerRadius: 24, style: .continuous)
                        .fill(Color.white.opacity(0.04))
                        .frame(height: 360)
                        .overlay {
                            VStack(spacing: 12) {
                                ProgressView()
                                    .tint(.white)
                                Text("Rendering share image…")
                                    .font(.subheadline)
                                    .foregroundColor(.white.opacity(0.72))
                            }
                        }
                } else {
                    RoundedRectangle(cornerRadius: 24, style: .continuous)
                        .fill(Color.white.opacity(0.04))
                        .frame(height: 220)
                        .overlay {
                            Text(renderError ?? "Preview unavailable")
                                .font(.subheadline)
                                .foregroundColor(.white.opacity(0.72))
                                .multilineTextAlignment(.center)
                                .padding()
                        }
                }
            }
        }
    }

    private var captionControls: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Caption")
                .font(.headline)
                .foregroundColor(.white)

            if ShareCaptionStyle.availableCases.count > 1 {
                Picker("Style", selection: $selectedCaptionStyle) {
                    ForEach(ShareCaptionStyle.availableCases) { style in
                        Text(style.title).tag(style)
                    }
                }
                .pickerStyle(.segmented)
            }

            TextEditor(text: $editableCaption)
                .frame(minHeight: 132)
                .scrollContentBackground(.hidden)
                .padding(10)
                .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                .foregroundColor(.white)
                .overlay(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )

            if !plusUnlocked {
                VStack(alignment: .leading, spacing: 8) {
                    Label("Basic sharing is included", systemImage: "sparkles")
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(.white)
                    Text("Free shares use the built-in Gaia Eyes card and caption. Plus unlocks the full background and caption packs.")
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.68))
                    NavigationLink(destination: SubscribeView()) {
                        Text("View Plus")
                            .font(.caption.weight(.semibold))
                    }
                    .buttonStyle(.bordered)
                    .tint(Color(red: 0.48, green: 0.73, blue: 1.0))
                }
                .padding(12)
                .background(Color.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
            }

            HStack(spacing: 10) {
                Button {
                    #if canImport(UIKit)
                    UIPasteboard.general.string = editableCaption
                    #endif
                } label: {
                    Label("Copy", systemImage: "doc.on.doc")
                }
                .buttonStyle(.bordered)
                .tint(.white.opacity(0.85))

                Spacer()

                Button {
                    showShareSheet = true
                } label: {
                    Label("Share", systemImage: "square.and.arrow.up")
                }
                .buttonStyle(.borderedProminent)
                .disabled(renderedImage == nil || isRendering)
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }

    private func loadShareCopyOverrideIfNeeded() async {
        guard !copyOverrideRequested else { return }
        copyOverrideRequested = true
        guard plusUnlocked else { return }

        do {
            let envelope: ShareCopyOverrideEnvelope = try await state.apiWithAuth().getJSON(
                shareCopyEndpointPath(),
                as: ShareCopyOverrideEnvelope.self,
                retries: 0,
                perRequestTimeout: 4
            )
            guard let copy = envelope.copy else { return }
            copyOverride = copy
            editableCaption = draft.applying(copyOverride: copy).captions.text(for: selectedCaptionStyle)
        } catch {
            // Remote copy is optional launch-time content. Keep the local draft as the fallback.
        }
    }

    private func shareCopyEndpointPath() -> String {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "share_type", value: draft.shareType.rawValue),
            URLQueryItem(name: "surface", value: draft.surface),
            URLQueryItem(name: "mode", value: "all"),
            URLQueryItem(name: "tone", value: selectedCaptionStyle.rawValue),
        ]
        let key = (draft.analyticsKey ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !key.isEmpty {
            queryItems.append(URLQueryItem(name: "key", value: key))
        }

        var components = URLComponents()
        components.queryItems = queryItems
        return "v1/profile/share-copy?\(components.percentEncodedQuery ?? "")"
    }

    private func renderPreview(force: Bool = false) async {
        if isRendering && !force {
            return
        }
        isRendering = true
        renderError = nil
        let draftToRender = activeDraft

        #if canImport(UIKit)
        let backgroundImage = await ShareBackgroundResolver.loadImage(for: draftToRender.card.background, scope: shareImageScope)
        let image = await MainActor.run {
            ShareCardRenderer.render(card: draftToRender.card, backgroundImage: backgroundImage)
        }
        renderedImage = image
        if image != nil {
            AppAnalytics.track(
                "share_rendered",
                properties: [
                    "share_type": draft.shareType.rawValue,
                    "surface": draft.surface,
                    "key": draft.analyticsKey ?? "unknown",
                ]
            )
        } else {
            renderError = "The share card could not be rendered."
        }
        #else
        renderError = "Sharing is unavailable on this device."
        #endif

        isRendering = false
    }
}
