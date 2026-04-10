import Foundation
import SwiftUI

enum ShareType: String, Codable, CaseIterable, Hashable {
    case signalSnapshot = "signal_snapshot"
    case personalPattern = "personal_pattern"
    case dailyState = "daily_state"
    case event
    case outlook
}

enum ShareCardLayout: String, Codable, Hashable {
    case signalSnapshot = "signal_snapshot"
    case personalPattern = "personal_pattern"
    case dailyState = "daily_state"
    case event
    case outlook
}

enum ShareCaptionStyle: String, Codable, CaseIterable, Hashable, Identifiable {
    case scientific
    case balanced
    case humorous

    var id: String { rawValue }

    var title: String {
        switch self {
        case .scientific:
            return "Scientific"
        case .balanced:
            return "Balanced"
        case .humorous:
            return "Humorous"
        }
    }
}

enum ShareAccentLevel: String, Codable, Hashable {
    case calm
    case watch
    case elevated
    case storm

    var tint: Color {
        switch self {
        case .calm:
            return GaugePalette.low
        case .watch:
            return GaugePalette.mild
        case .elevated:
            return GaugePalette.elevated
        case .storm:
            return GaugePalette.high
        }
    }

    var pillTitle: String {
        switch self {
        case .calm:
            return "Calm"
        case .watch:
            return "Watch"
        case .elevated:
            return "Elevated"
        case .storm:
            return "Storm"
        }
    }
}

enum ShareCardFormat: String, Codable, Hashable {
    case square
    case portrait
    case landscape

    var canvasSize: CGSize {
        switch self {
        case .square:
            return CGSize(width: 360, height: 360)
        case .portrait:
            return CGSize(width: 360, height: 640)
        case .landscape:
            return CGSize(width: 640, height: 360)
        }
    }
}

enum ShareBackgroundStyle: String, Codable, Hashable {
    case schumann
    case solar
    case cme
    case atmospheric
    case abstract
}

struct ShareBranding: Hashable {
    let title: String
    let subtitle: String
    let url: String

    static let gaiaEyes = ShareBranding(
        title: "Gaia Eyes",
        subtitle: "Environmental signal interpretation",
        url: "gaiaeyes.app"
    )
}

struct ShareCardChip: Identifiable, Hashable {
    let id: String
    let label: String
    let value: String
}

struct ShareCardBackground: Hashable {
    let style: ShareBackgroundStyle
    let candidateURLs: [URL]
    let themeKeys: [String]

    init(style: ShareBackgroundStyle, candidateURLs: [URL] = [], themeKeys: [String] = []) {
        self.style = style
        self.candidateURLs = candidateURLs
        self.themeKeys = themeKeys
    }
}

struct ShareCardModel: Identifiable, Hashable {
    let id = UUID()
    let shareType: ShareType
    let layout: ShareCardLayout
    let format: ShareCardFormat
    let background: ShareCardBackground
    let accentLevel: ShareAccentLevel
    let eyebrow: String?
    let title: String
    let subtitle: String?
    let signText: String?
    let primaryText: String?
    let valueText: String?
    let stateText: String?
    let bullets: [String]
    let highlights: [ShareCardChip]
    let note: String?
    let footer: String
    let sourceLine: String?
    let branding: ShareBranding
}

struct ShareCaptionSet: Hashable {
    let scientific: String
    let balanced: String
    let humorous: String

    func text(for style: ShareCaptionStyle) -> String {
        switch style {
        case .scientific:
            return scientific
        case .balanced:
            return balanced
        case .humorous:
            return humorous
        }
    }
}

struct ShareDraft: Identifiable, Hashable {
    let id = UUID()
    let shareType: ShareType
    let surface: String
    let analyticsKey: String?
    let promptText: String?
    let card: ShareCardModel
    let captions: ShareCaptionSet
}

struct ShareHistoryEntry: Codable, Hashable, Identifiable {
    let id: String
    let shareType: ShareType
    let surface: String
    let key: String?
    let timestamp: String
}
