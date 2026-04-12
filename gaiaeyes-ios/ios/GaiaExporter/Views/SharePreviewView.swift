import SwiftUI

#if canImport(UIKit)
import UIKit
#endif

struct SharePreviewView: View {
    let draft: ShareDraft

    @Environment(\.dismiss) private var dismiss
    @AppStorage("gaia.membership.cached_plan") private var cachedPlanRaw: String = MembershipPlan.free.rawValue
    @State private var selectedCaptionStyle: ShareCaptionStyle = .balanced
    @State private var editableCaption: String
    @State private var renderedImage: UIImage?
    @State private var isRendering: Bool = false
    @State private var renderError: String?
    @State private var showShareSheet: Bool = false
    @State private var hasTrackedOpen: Bool = false

    init(draft: ShareDraft) {
        self.draft = draft
        _editableCaption = State(initialValue: draft.captions.text(for: .balanced))
    }

    private var plusUnlocked: Bool {
        let plan = MembershipPlan(rawValue: cachedPlanRaw) ?? .free
        return plan == .plus || plan == .pro
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
                await renderPreview()
            }
            .onChange(of: selectedCaptionStyle, initial: false) { _, newValue in
                editableCaption = draft.captions.text(for: newValue)
            }
            .sheet(isPresented: $showShareSheet) {
                if let renderedImage {
                    ShareSheetPresenter(
                        image: renderedImage,
                        text: editableCaption,
                        title: draft.card.title,
                        subtitle: draft.card.subtitle
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

            Picker("Style", selection: $selectedCaptionStyle) {
                ForEach(ShareCaptionStyle.allCases) { style in
                    Text(style.title).tag(style)
                }
            }
            .pickerStyle(.segmented)

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
                    Label("Sharing is included with Plus", systemImage: "lock.fill")
                        .font(.subheadline.weight(.semibold))
                        .foregroundColor(.white)
                    Text("You can preview the card for free. Upgrade to publish it through the share sheet.")
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
                .disabled(renderedImage == nil || isRendering || !plusUnlocked)
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.04), in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }

    private func renderPreview(force: Bool = false) async {
        if isRendering && !force {
            return
        }
        isRendering = true
        renderError = nil

        #if canImport(UIKit)
        let backgroundImage = await ShareBackgroundResolver.loadImage(for: draft.card.background)
        let image = await MainActor.run {
            ShareCardRenderer.render(card: draft.card, backgroundImage: backgroundImage)
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
