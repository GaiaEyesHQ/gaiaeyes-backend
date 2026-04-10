import SwiftUI

#if canImport(UIKit)
import UIKit
#endif

struct ShareCardView: View {
    let model: ShareCardModel
    let backgroundImage: UIImage?

    private var accentColor: Color {
        model.accentLevel.tint
    }

    private var padding: CGFloat {
        switch model.format {
        case .square:
            return 22
        case .portrait:
            return 24
        case .landscape:
            return 20
        }
    }

    var body: some View {
        ZStack {
            ShareCardBackgroundView(
                background: model.background,
                accentLevel: model.accentLevel,
                backgroundImage: backgroundImage
            )

            LinearGradient(
                colors: [
                    Color.black.opacity(0.08),
                    Color.black.opacity(0.24),
                    Color.black.opacity(0.66)
                ],
                startPoint: .top,
                endPoint: .bottom
            )

            VStack(alignment: .leading, spacing: 14) {
                topBar
                Spacer(minLength: 0)
                contentBlock
                footerBlock
            }
            .padding(padding)
        }
        .clipShape(RoundedRectangle(cornerRadius: 32, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 32, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
        .background(Color.black)
    }

    private var topBar: some View {
        HStack(alignment: .top, spacing: 12) {
            if let eyebrow = model.eyebrow, !eyebrow.isEmpty {
                Text(eyebrow.uppercased())
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundColor(.white.opacity(0.72))
                    .tracking(0.8)
                    .lineLimit(1)
            }
            Spacer()
            if let pillLabel = activePillLabel {
                ShareStatePill(label: pillLabel, tint: accentColor)
            }
        }
    }

    private var contentBlock: some View {
        if usesMinimalHeroLayout {
            return AnyView(minimalContentBlock)
        }
        return AnyView(legacyContentBlock)
    }

    private var legacyContentBlock: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.title)
                .font(.system(size: titleSize, weight: .bold, design: .rounded))
                .foregroundColor(.white)
                .lineLimit(2)
                .minimumScaleFactor(0.72)
                .fixedSize(horizontal: false, vertical: true)

            if let signText = model.signText, !signText.isEmpty {
                Text(signText)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundColor(.white.opacity(0.94))
                    .lineSpacing(1)
                    .lineLimit(2)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(accentColor.opacity(0.16), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(accentColor.opacity(0.34), lineWidth: 1)
                    )
            }

            if let subtitle = model.subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.system(size: 17, weight: .medium, design: .rounded))
                    .foregroundColor(.white.opacity(0.82))
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let valueText = model.valueText, !valueText.isEmpty {
                Text(valueText)
                    .font(.system(size: valueSize, weight: .heavy, design: .rounded))
                    .foregroundColor(.white)
                    .minimumScaleFactor(0.72)
                    .lineLimit(2)
            }

            if let primaryText = model.primaryText, !primaryText.isEmpty {
                Text(primaryText)
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                    .foregroundColor(.white.opacity(0.94))
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !model.highlights.isEmpty {
                ShareHighlightsView(highlights: model.highlights, tint: accentColor)
            }

            if !model.bullets.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(Array(model.bullets.prefix(2).enumerated()), id: \.offset) { _, bullet in
                        HStack(alignment: .top, spacing: 8) {
                            Circle()
                                .fill(accentColor)
                                .frame(width: 7, height: 7)
                                .padding(.top, 6)
                            Text(bullet)
                                .font(.system(size: 15, weight: .medium, design: .rounded))
                                .foregroundColor(.white.opacity(0.88))
                                .lineLimit(2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }

            if let note = model.note, !note.isEmpty {
                Text(note)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundColor(.white.opacity(0.72))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var minimalContentBlock: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(model.title)
                .font(.system(size: titleSize + 2, weight: .bold, design: .rounded))
                .foregroundColor(.white)
                .lineLimit(3)
                .minimumScaleFactor(0.76)
                .fixedSize(horizontal: false, vertical: true)

            if let primaryText = model.primaryText?.trimmingCharacters(in: .whitespacesAndNewlines), !primaryText.isEmpty {
                Text(primaryText.uppercased())
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundColor(.white.opacity(0.68))
                    .tracking(0.9)
                    .lineLimit(1)
            }

            if let valueText = model.valueText?.trimmingCharacters(in: .whitespacesAndNewlines), !valueText.isEmpty {
                Text(valueText)
                    .font(.system(size: valueSize + 10, weight: .heavy, design: .rounded))
                    .foregroundColor(.white)
                    .minimumScaleFactor(0.72)
                    .lineLimit(2)
            }

            if let note = minimalNoteText {
                Text(note)
                    .font(.system(size: 14, weight: .medium, design: .rounded))
                    .foregroundColor(.white.opacity(0.84))
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var footerBlock: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let sourceLine = model.sourceLine, !sourceLine.isEmpty {
                Text(sourceLine)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundColor(.white.opacity(0.62))
                    .lineLimit(1)
            }

            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(model.branding.title)
                        .font(.system(size: 13, weight: .bold, design: .rounded))
                        .foregroundColor(.white.opacity(0.92))
                    Text(model.branding.url)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundColor(.white.opacity(0.56))
                        .lineLimit(1)
                }

                Spacer()

                Text(model.footer)
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundColor(.white.opacity(0.66))
                    .lineLimit(1)
                    .minimumScaleFactor(0.82)
                    .multilineTextAlignment(.trailing)
            }
        }
    }

    private var titleSize: CGFloat {
        switch model.layout {
        case .personalPattern:
            return 24
        case .dailyState:
            return 28
        default:
            return 28
        }
    }

    private var valueSize: CGFloat {
        switch model.format {
        case .square:
            return 38
        case .portrait:
            return 42
        case .landscape:
            return 34
        }
    }

    private var activePillLabel: String? {
        let state = model.stateText?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let state, !state.isEmpty {
            return state
        }
        return model.accentLevel.pillTitle
    }

    private var usesMinimalHeroLayout: Bool {
        switch model.layout {
        case .signalSnapshot, .dailyState, .event, .outlook:
            return true
        case .personalPattern:
            return false
        }
    }

    private var minimalNoteText: String? {
        if let note = model.note?.trimmingCharacters(in: .whitespacesAndNewlines), !note.isEmpty {
            return note
        }
        if let subtitle = model.subtitle?.trimmingCharacters(in: .whitespacesAndNewlines), !subtitle.isEmpty {
            return subtitle
        }
        return nil
    }
}

private struct ShareHighlightsView: View {
    let highlights: [ShareCardChip]
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(highlights.prefix(2).enumerated()), id: \.offset) { _, highlight in
                HStack {
                    Text(highlight.label.uppercased())
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundColor(.white.opacity(0.56))
                    Spacer()
                    Text(highlight.value)
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundColor(.white.opacity(0.92))
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .background(tint.opacity(0.15), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .stroke(tint.opacity(0.30), lineWidth: 1)
                )
            }
        }
    }
}

private struct ShareStatePill: View {
    let label: String
    let tint: Color

    var body: some View {
        Text(label)
            .font(.system(size: 11, weight: .bold, design: .rounded))
            .foregroundColor(.white.opacity(0.92))
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(tint.opacity(0.18), in: Capsule())
            .overlay(
                Capsule()
                    .stroke(tint.opacity(0.44), lineWidth: 1)
            )
    }
}

private struct ShareCardBackgroundView: View {
    let background: ShareCardBackground
    let accentLevel: ShareAccentLevel
    let backgroundImage: UIImage?

    var body: some View {
        ZStack {
            if let backgroundImage {
                Image(uiImage: backgroundImage)
                    .resizable()
                    .scaledToFill()
            } else {
                generatedFallback
            }
        }
        .overlay(accentOverlay)
    }

    private var accentOverlay: some View {
        LinearGradient(
            colors: [
                accentLevel.tint.opacity(0.24),
                Color.clear,
                Color.black.opacity(0.10)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    @ViewBuilder
    private var generatedFallback: some View {
        switch background.style {
        case .schumann:
            ZStack {
                LinearGradient(
                    colors: [Color(red: 0.06, green: 0.10, blue: 0.18), Color(red: 0.14, green: 0.09, blue: 0.24)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                VStack(spacing: 20) {
                    ForEach(0..<7, id: \.self) { index in
                        Capsule()
                            .fill(Color.white.opacity(index.isMultiple(of: 2) ? 0.10 : 0.05))
                            .frame(height: CGFloat(10 + (index * 4)))
                            .blur(radius: CGFloat(index) * 1.3)
                    }
                }
                .rotationEffect(.degrees(-12))
                .offset(x: 30, y: 10)
            }
        case .solar:
            ZStack {
                LinearGradient(
                    colors: [Color(red: 0.10, green: 0.06, blue: 0.10), Color(red: 0.28, green: 0.10, blue: 0.07)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                Circle()
                    .fill(
                        RadialGradient(
                            colors: [Color.orange.opacity(0.96), Color.red.opacity(0.14), Color.clear],
                            center: .center,
                            startRadius: 18,
                            endRadius: 180
                        )
                    )
                    .frame(width: 240, height: 240)
                    .offset(x: 90, y: -90)
                Circle()
                    .stroke(Color.white.opacity(0.14), lineWidth: 2)
                    .frame(width: 280, height: 280)
                    .offset(x: 88, y: -88)
            }
        case .cme:
            ZStack {
                LinearGradient(
                    colors: [Color(red: 0.05, green: 0.07, blue: 0.12), Color(red: 0.16, green: 0.07, blue: 0.11)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                Circle()
                    .fill(Color.orange.opacity(0.85))
                    .frame(width: 110, height: 110)
                    .blur(radius: 4)
                    .offset(x: 92, y: -96)
                ForEach(0..<3, id: \.self) { index in
                    Circle()
                        .stroke(Color.white.opacity(0.08 + (Double(index) * 0.04)), lineWidth: CGFloat(22 - (index * 5)))
                        .frame(width: CGFloat(240 + (index * 40)), height: CGFloat(240 + (index * 40)))
                        .scaleEffect(x: 1.2, y: 0.7)
                        .offset(x: 100, y: -40)
                }
            }
        case .atmospheric:
            ZStack {
                LinearGradient(
                    colors: [Color(red: 0.09, green: 0.16, blue: 0.22), Color(red: 0.11, green: 0.18, blue: 0.13)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                Circle()
                    .fill(Color.white.opacity(0.10))
                    .frame(width: 240, height: 240)
                    .blur(radius: 34)
                    .offset(x: -80, y: -120)
                Circle()
                    .fill(Color.cyan.opacity(0.12))
                    .frame(width: 260, height: 260)
                    .blur(radius: 40)
                    .offset(x: 120, y: 120)
            }
        case .abstract:
            ZStack {
                LinearGradient(
                    colors: [Color(red: 0.07, green: 0.09, blue: 0.16), Color(red: 0.11, green: 0.12, blue: 0.20)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
                RoundedRectangle(cornerRadius: 40, style: .continuous)
                    .fill(accentLevel.tint.opacity(0.16))
                    .frame(width: 240, height: 240)
                    .blur(radius: 40)
                    .offset(x: 110, y: -120)
                Circle()
                    .fill(Color.white.opacity(0.08))
                    .frame(width: 190, height: 190)
                    .blur(radius: 24)
                    .offset(x: -120, y: 120)
            }
        }
    }
}
