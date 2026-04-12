import SwiftUI

struct GuideEntryButton: View {
    let guideType: GuideType
    var hasUnseen: Bool = false
    let action: () -> Void
    @State private var isPulsing: Bool = false

    var body: some View {
        ZStack {
            if hasUnseen {
                Circle()
                    .fill(Color(red: 0.25, green: 0.84, blue: 0.98).opacity(0.24))
                    .frame(width: 42, height: 42)
                    .blur(radius: 6)
                    .scaleEffect(isPulsing ? 1.36 : 1.02)

                Circle()
                    .stroke(Color(red: 0.32, green: 0.90, blue: 0.98).opacity(0.72), lineWidth: 1.6)
                    .frame(width: 40, height: 40)
                    .blur(radius: 0.4)
                    .scaleEffect(isPulsing ? 1.24 : 0.96)
            }

            GuideAvatarView(
                guide: guideType,
                expression: .subtle,
                size: .small,
                emphasis: hasUnseen ? .active : .standard,
                showBackingPlate: false,
                animate: hasUnseen
            )
            .scaleEffect(1.34)
        }
        .frame(minWidth: 50, minHeight: 50)
        .overlay(alignment: .topTrailing) {
            if hasUnseen {
                Circle()
                    .fill(Color(red: 0.30, green: 0.79, blue: 0.98))
                    .frame(width: 10, height: 10)
                    .overlay(
                        Circle()
                            .stroke(Color.black.opacity(0.45), lineWidth: 1)
                    )
                    .shadow(color: Color(red: 0.25, green: 0.84, blue: 0.98).opacity(0.65), radius: 6)
                    .offset(x: 3, y: -2)
                    .accessibilityHidden(true)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture(perform: action)
        .onAppear {
            guard hasUnseen else { return }
            withAnimation(.easeInOut(duration: 1.35).repeatForever(autoreverses: true)) {
                isPulsing = true
            }
        }
        .onChange(of: hasUnseen) { _, newValue in
            if newValue {
                isPulsing = false
                withAnimation(.easeInOut(duration: 1.35).repeatForever(autoreverses: true)) {
                    isPulsing = true
                }
            } else {
                isPulsing = false
            }
        }
        .accessibilityLabel("Guide")
        .accessibilityHint(hasUnseen ? "Open Guide Hub with new updates" : "Open Guide Hub")
        .accessibilityAddTraits(.isButton)
    }
}
