import SwiftUI

struct GuideEntryButton: View {
    let guideType: GuideType
    var hasUnseen: Bool = false
    let action: () -> Void

    var body: some View {
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
        .frame(width: 54, height: 54)
        .contentShape(Rectangle())
        .onTapGesture(perform: action)
        .accessibilityLabel("Guide")
        .accessibilityHint(hasUnseen ? "Open Guide Hub with new updates" : "Open Guide Hub")
        .accessibilityAddTraits(.isButton)
    }
}
