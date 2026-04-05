import SwiftUI

struct GuideHubSectionCard<Content: View>: View {
    let guideType: GuideType
    let expression: GuideExpression
    let emphasis: GuideAvatarEmphasis
    let eyebrow: String?
    let title: String
    let message: String
    let badgeText: String?
    let primaryActionTitle: String?
    let primaryAction: (() -> Void)?
    let secondaryActionTitle: String?
    let secondaryAction: (() -> Void)?
    let content: Content

    init(
        guideType: GuideType,
        expression: GuideExpression,
        emphasis: GuideAvatarEmphasis = .standard,
        eyebrow: String? = nil,
        title: String,
        message: String,
        badgeText: String? = nil,
        primaryActionTitle: String? = nil,
        primaryAction: (() -> Void)? = nil,
        secondaryActionTitle: String? = nil,
        secondaryAction: (() -> Void)? = nil,
        @ViewBuilder content: () -> Content = { EmptyView() }
    ) {
        self.guideType = guideType
        self.expression = expression
        self.emphasis = emphasis
        self.eyebrow = eyebrow
        self.title = title
        self.message = message
        self.badgeText = badgeText
        self.primaryActionTitle = primaryActionTitle
        self.primaryAction = primaryAction
        self.secondaryActionTitle = secondaryActionTitle
        self.secondaryAction = secondaryAction
        self.content = content()
    }

    var body: some View {
        let style = GuidePromptStyle.style(for: guideType, emphasis: emphasis)

        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 14) {
                GuideAvatarView(
                    guide: guideType,
                    expression: expression,
                    size: .medium,
                    emphasis: emphasis,
                    showBackingPlate: false,
                    showGlow: false,
                    sizeMultiplier: 1.3
                )

                VStack(alignment: .leading, spacing: 6) {
                    if let eyebrow, !eyebrow.isEmpty {
                        Text(eyebrow.uppercased())
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(style.tertiaryText)
                    }
                    Text(title)
                        .font(.headline)
                        .foregroundStyle(style.primaryText)
                    Text(message)
                        .font(.subheadline)
                        .foregroundStyle(style.secondaryText)
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 0)

                if let badgeText, !badgeText.isEmpty {
                    Text(badgeText)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(style.primaryText)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(style.accent.opacity(0.18), in: Capsule())
                }
            }

            content

            if primaryActionTitle != nil || secondaryActionTitle != nil {
                HStack(spacing: 10) {
                    if let primaryActionTitle, let primaryAction {
                        Button(primaryActionTitle, action: primaryAction)
                            .buttonStyle(.borderedProminent)
                            .tint(style.accent)
                    }
                    if let secondaryActionTitle, let secondaryAction {
                        Button(secondaryActionTitle, action: secondaryAction)
                            .buttonStyle(.bordered)
                            .tint(style.accent)
                    }
                }
            }
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(style.cardFill, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(style.cardBorder, lineWidth: 1)
        )
        .shadow(color: style.glow, radius: emphasis == .active ? 18 : 12)
    }
}
