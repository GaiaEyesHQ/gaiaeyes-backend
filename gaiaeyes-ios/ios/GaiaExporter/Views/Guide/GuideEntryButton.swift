import SwiftUI

struct GuideEntryButton: View {
    let guideType: GuideType
    let action: () -> Void

    var body: some View {
        GuideAvatarView(
            guide: guideType,
            expression: .subtle,
            size: .small,
            emphasis: .standard,
            showBackingPlate: false
        )
        .scaleEffect(1.15)
        .frame(minWidth: 44, minHeight: 44)
        .contentShape(Rectangle())
        .onTapGesture(perform: action)
        .accessibilityLabel("Guide")
        .accessibilityHint("Open Guide Hub")
        .accessibilityAddTraits(.isButton)
    }
}
