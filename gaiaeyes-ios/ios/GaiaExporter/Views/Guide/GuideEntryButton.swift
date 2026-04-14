import SwiftUI

struct GuideEntryButton: View {
    let guideType: GuideType
    var hasUnseen: Bool = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            GuideAvatarView(
                guide: guideType,
                expression: .guide,
                size: .small,
                emphasis: hasUnseen ? .active : .standard,
                showBackingPlate: false,
                showGlow: hasUnseen,
                sizeMultiplier: 1.34,
                animate: hasUnseen
            )
            .frame(width: 62, height: 62)
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Guide")
        .accessibilityHint(hasUnseen ? "Open Guide Hub with new updates" : "Open Guide Hub")
    }
}
