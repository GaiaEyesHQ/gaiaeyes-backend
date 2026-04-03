import SwiftUI

struct GuideEntryButton: View {
    let guideType: GuideType
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            GuideAvatarView(
                guide: guideType,
                expression: .subtle,
                size: .small,
                emphasis: .standard,
                showBackingPlate: false
            )
            .frame(minWidth: 44, minHeight: 44)
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Guide")
        .accessibilityHint("Open Guide Hub")
    }
}
