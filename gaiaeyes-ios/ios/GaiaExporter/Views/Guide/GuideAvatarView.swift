import SwiftUI

enum GuideExpression: String, Codable, CaseIterable {
    case neutral
    case calm
    case alert
    case curious
    case helpful
    case followUp
    case subtle
    case playful
    case guide
}

enum GuideAvatarSize {
    case micro
    case small
    case medium
    case large
    case hero
}

extension GuideAvatarSize {
    var dimension: CGFloat {
        switch self {
        case .micro:
            return 22
        case .small:
            return 32
        case .medium:
            return 48
        case .large:
            return 72
        case .hero:
            return 124
        }
    }

    var glowPadding: CGFloat {
        switch self {
        case .micro:
            return 4
        case .small:
            return 6
        case .medium:
            return 8
        case .large:
            return 10
        case .hero:
            return 14
        }
    }

    var backingPlateScale: CGFloat {
        switch self {
        case .micro:
            return 1.32
        case .small:
            return 1.36
        case .medium:
            return 1.38
        case .large:
            return 1.42
        case .hero:
            return 1.48
        }
    }
}

enum GuideAvatarEmphasis {
    case quiet
    case standard
    case elevated
    case active
}

private struct GuideAvatarGlowStyle {
    let color: Color
    let outerOpacity: Double
    let outerRadius: CGFloat
    let innerOpacity: Double
    let innerRadius: CGFloat
    let backingFillOpacity: Double
    let backingStrokeOpacity: Double
}

extension GuideAvatarEmphasis {
    fileprivate var glowStyle: GuideAvatarGlowStyle {
        switch self {
        case .quiet:
            return GuideAvatarGlowStyle(
                color: Color(red: 0.34, green: 0.66, blue: 0.95),
                outerOpacity: 0.14,
                outerRadius: 10,
                innerOpacity: 0.08,
                innerRadius: 4,
                backingFillOpacity: 0.22,
                backingStrokeOpacity: 0.10
            )
        case .standard:
            return GuideAvatarGlowStyle(
                color: Color(red: 0.30, green: 0.79, blue: 0.98),
                outerOpacity: 0.24,
                outerRadius: 14,
                innerOpacity: 0.12,
                innerRadius: 6,
                backingFillOpacity: 0.26,
                backingStrokeOpacity: 0.14
            )
        case .elevated:
            return GuideAvatarGlowStyle(
                color: Color(red: 0.28, green: 0.84, blue: 0.98),
                outerOpacity: 0.34,
                outerRadius: 18,
                innerOpacity: 0.18,
                innerRadius: 8,
                backingFillOpacity: 0.30,
                backingStrokeOpacity: 0.18
            )
        case .active:
            return GuideAvatarGlowStyle(
                color: Color(red: 0.26, green: 0.88, blue: 0.92),
                outerOpacity: 0.42,
                outerRadius: 22,
                innerOpacity: 0.22,
                innerRadius: 10,
                backingFillOpacity: 0.34,
                backingStrokeOpacity: 0.22
            )
        }
    }
}

struct GuideAvatarView: View {
    let guide: GuideType
    let expression: GuideExpression
    let size: GuideAvatarSize
    let emphasis: GuideAvatarEmphasis
    var tintMode: GuideAvatarTintMode = .fullColor
    var showBackingPlate: Bool = false
    var showGlow: Bool = true
    var sizeMultiplier: CGFloat = 1.0
    var animate: Bool = false

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var hasAnimatedIn: Bool = false

    private var assetName: String {
        GuideAssetResolver.assetName(for: guide, expression: expression, size: size)
    }

    private var glowStyle: GuideAvatarGlowStyle {
        emphasis.glowStyle
    }

    private var effectiveGlowPadding: CGFloat {
        showGlow ? size.glowPadding : 0
    }

    private var shouldAnimate: Bool {
        animate && !reduceMotion
    }

    private var contentScale: CGFloat {
        shouldAnimate ? (hasAnimatedIn ? 1 : 0.94) : 1
    }

    private var contentOpacity: Double {
        shouldAnimate ? (hasAnimatedIn ? 1 : 0) : 1
    }

    private var tintOpacity: Double {
        switch tintMode {
        case .fullColor:
            return 1
        case .softened:
            return 0.9
        }
    }

    private var tintSaturation: Double {
        switch tintMode {
        case .fullColor:
            return 1
        case .softened:
            return 0.92
        }
    }

    var body: some View {
        ZStack {
            if showBackingPlate {
                Circle()
                    .fill(Color.white.opacity(glowStyle.backingFillOpacity))
                    .overlay(
                        Circle()
                            .stroke(glowStyle.color.opacity(glowStyle.backingStrokeOpacity), lineWidth: 1)
                    )
                    .frame(
                        width: size.dimension * size.backingPlateScale * sizeMultiplier,
                        height: size.dimension * size.backingPlateScale * sizeMultiplier
                    )
            }

            Image(assetName)
                .resizable()
                .renderingMode(.original)
                .interpolation(.high)
                .scaledToFit()
                .frame(width: size.dimension * sizeMultiplier, height: size.dimension * sizeMultiplier)
                .scaleEffect(contentScale)
                .opacity(contentOpacity * tintOpacity)
                .saturation(tintSaturation)
                .shadow(
                    color: showGlow ? glowStyle.color.opacity(glowStyle.outerOpacity) : .clear,
                    radius: showGlow ? glowStyle.outerRadius : 0
                )
                .shadow(
                    color: showGlow ? glowStyle.color.opacity(glowStyle.innerOpacity) : .clear,
                    radius: showGlow ? glowStyle.innerRadius : 0
                )
        }
        .frame(
            width: (size.dimension + (effectiveGlowPadding * 2)) * sizeMultiplier,
            height: (size.dimension + (effectiveGlowPadding * 2)) * sizeMultiplier
        )
        .contentShape(Circle())
        .accessibilityHidden(true)
        .onAppear {
            guard shouldAnimate else {
                hasAnimatedIn = true
                return
            }
            guard !hasAnimatedIn else { return }
            withAnimation(.easeOut(duration: emphasis == .active ? 0.34 : 0.26)) {
                hasAnimatedIn = true
            }
        }
    }
}

#if DEBUG
private struct GuideAvatarPreviewGallery: View {
    private struct PreviewItem: Identifiable {
        let title: String
        let guide: GuideType
        let expression: GuideExpression
        let size: GuideAvatarSize
        let emphasis: GuideAvatarEmphasis
        let showBackingPlate: Bool
        let animate: Bool

        var id: String { title }
    }

    private let items: [PreviewItem] = [
        PreviewItem(title: "Cat neutral • micro", guide: .cat, expression: .neutral, size: .micro, emphasis: .quiet, showBackingPlate: false, animate: false),
        PreviewItem(title: "Cat calm • medium", guide: .cat, expression: .calm, size: .medium, emphasis: .standard, showBackingPlate: false, animate: false),
        PreviewItem(title: "Cat alert • elevated", guide: .cat, expression: .alert, size: .medium, emphasis: .elevated, showBackingPlate: false, animate: false),
        PreviewItem(title: "Cat curious • backing", guide: .cat, expression: .curious, size: .small, emphasis: .standard, showBackingPlate: true, animate: false),
        PreviewItem(title: "Cat portrait • hero", guide: .cat, expression: .guide, size: .hero, emphasis: .active, showBackingPlate: false, animate: false),
        PreviewItem(title: "Dog fallback", guide: .dog, expression: .helpful, size: .medium, emphasis: .standard, showBackingPlate: true, animate: false),
        PreviewItem(title: "Robot fallback", guide: .robot, expression: .guide, size: .medium, emphasis: .elevated, showBackingPlate: true, animate: false)
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Guide Avatar Gallery")
                    .font(.title3.weight(.semibold))
                    .foregroundStyle(.white.opacity(0.92))

                ForEach(items) { item in
                    HStack(spacing: 16) {
                        GuideAvatarView(
                            guide: item.guide,
                            expression: item.expression,
                            size: item.size,
                            emphasis: item.emphasis,
                            showBackingPlate: item.showBackingPlate,
                            animate: item.animate
                        )

                        Text(item.title)
                            .font(.headline)
                            .foregroundStyle(.white.opacity(0.86))
                        Spacer()
                    }
                    .padding(14)
                    .background(Color.white.opacity(0.05))
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.03, green: 0.05, blue: 0.10),
                    Color(red: 0.02, green: 0.03, blue: 0.08)
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
        )
    }
}

#Preview("Guide Avatar Gallery") {
    GuideAvatarPreviewGallery()
}
#endif
