import Foundation

enum ExperienceMode: String, CaseIterable, Codable, Identifiable {
    case scientific
    case mystical

    var id: String { rawValue }

    var title: String {
        switch self {
        case .scientific:
            return "Scientific"
        case .mystical:
            return "Mystical"
        }
    }

    var subtitle: String {
        switch self {
        case .scientific:
            return "metrics and research-style language"
        case .mystical:
            return "translated, intuitive guidance"
        }
    }
}

enum GuideType: String, CaseIterable, Codable, Identifiable {
    case cat
    case robot
    case dog

    var id: String { rawValue }

    var title: String { rawValue.capitalized }

    var subtitle: String {
        switch self {
        case .cat:
            return "calm, observant, and a little mysterious"
        case .robot:
            return "clear, precise, and data-forward"
        case .dog:
            return "steady, encouraging, and grounded"
        }
    }
}

enum ToneStyle: String, CaseIterable, Codable, Identifiable {
    case straight
    case balanced
    case humorous

    var id: String { rawValue }

    var title: String { rawValue.capitalized }

    var subtitle: String {
        switch self {
        case .straight:
            return "direct, concise, and factual"
        case .balanced:
            return "clear, warm, and grounded"
        case .humorous:
            return "light touches without losing trust"
        }
    }
}

enum TemperatureUnit: String, CaseIterable, Codable, Identifiable {
    case fahrenheit = "F"
    case celsius = "C"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .fahrenheit:
            return "Fahrenheit (\u{00B0}F)"
        case .celsius:
            return "Celsius (\u{00B0}C)"
        }
    }

    var subtitle: String {
        switch self {
        case .fahrenheit:
            return "US-style weather display"
        case .celsius:
            return "Metric weather display"
        }
    }

    var symbol: String {
        switch self {
        case .fahrenheit:
            return "\u{00B0}F"
        case .celsius:
            return "\u{00B0}C"
        }
    }

    static var localeDefault: TemperatureUnit {
        let region = (Locale.current.region?.identifier ?? "").uppercased()
        return region == "US" ? .fahrenheit : .celsius
    }
}

enum TrackedStatKey: String, CaseIterable, Codable, Identifiable {
    case restingHr = "resting_hr"
    case respiratory
    case spo2
    case hrv
    case temperature
    case steps
    case heartRange = "heart_range"
    case bloodPressure = "blood_pressure"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .restingHr:
            return "Resting HR"
        case .respiratory:
            return "Respiratory"
        case .spo2:
            return "SpO2"
        case .hrv:
            return "HRV"
        case .temperature:
            return "Temperature"
        case .steps:
            return "Steps"
        case .heartRange:
            return "Heart range"
        case .bloodPressure:
            return "Blood pressure"
        }
    }

    var subtitle: String {
        switch self {
        case .restingHr:
            return "Baseline shift or daily average"
        case .respiratory:
            return "Breathing-rate shift or average"
        case .spo2:
            return "Oxygen average"
        case .hrv:
            return "Recovery average"
        case .temperature:
            return "Temperature deviation"
        case .steps:
            return "Today’s activity"
        case .heartRange:
            return "Min and max heart rate"
        case .bloodPressure:
            return "Average blood pressure"
        }
    }

    static let defaultSelection: [TrackedStatKey] = [.restingHr, .respiratory, .hrv, .spo2, .steps]
    static let maxPinnedCount = 5
}

enum FavoriteSymptomPreference {
    static let maxCount = 6
}

enum OnboardingStep: String, CaseIterable, Codable, Identifiable {
    case welcome
    case mode
    case guide
    case tone
    case temperatureUnit = "temperature_unit"
    case sensitivities
    case healthContext = "health_context"
    case location
    case healthkit
    case backfill
    case notifications
    case activation

    var id: String { rawValue }

    static let ordered: [OnboardingStep] = [
        .welcome,
        .mode,
        .guide,
        .tone,
        .temperatureUnit,
        .sensitivities,
        .healthContext,
        .location,
        .healthkit,
        .backfill,
        .notifications,
        .activation,
    ]

    var progressValue: Double {
        guard let index = Self.ordered.firstIndex(of: self) else { return 0 }
        return Double(index + 1) / Double(Self.ordered.count)
    }

    func next() -> OnboardingStep? {
        guard let index = Self.ordered.firstIndex(of: self), index + 1 < Self.ordered.count else {
            return nil
        }
        return Self.ordered[index + 1]
    }

    func previous() -> OnboardingStep? {
        guard let index = Self.ordered.firstIndex(of: self), index > 0 else {
            return nil
        }
        return Self.ordered[index - 1]
    }
}

enum HealthPermissionOption: String, CaseIterable, Codable, Identifiable {
    case heartRate = "heart_rate"
    case heartRateVariability = "heart_rate_variability"
    case sleep
    case spo2
    case respiratoryRate = "respiratory_rate"
    case restingHeartRate = "resting_heart_rate"
    case bloodPressure = "blood_pressure"
    case wristTemperature = "wrist_temperature"
    case cycleTracking = "cycle_tracking"
    case stepCount = "step_count"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .heartRate:
            return "Heart rate"
        case .heartRateVariability:
            return "HRV"
        case .sleep:
            return "Sleep"
        case .spo2:
            return "SpO2"
        case .respiratoryRate:
            return "Respiratory rate"
        case .restingHeartRate:
            return "Resting heart rate"
        case .bloodPressure:
            return "Blood pressure"
        case .wristTemperature:
            return "Wrist temperature"
        case .cycleTracking:
            return "Cycle tracking"
        case .stepCount:
            return "Steps"
        }
    }

    var subtitle: String {
        switch self {
        case .heartRate:
            return "Daily body load and current-state context."
        case .heartRateVariability:
            return "Recovery and nervous-system resilience trends."
        case .sleep:
            return "Sleep timing and disruption context."
        case .spo2:
            return "Oxygen trend context when available."
        case .respiratoryRate:
            return "Breathing-rate shifts during sleep and recovery."
        case .restingHeartRate:
            return "Baseline recovery and strain context."
        case .bloodPressure:
            return "Blood-pressure changes when your device supports it."
        case .wristTemperature:
            return "Wrist temperature deviation when supported."
        case .cycleTracking:
            return "Menstrual-flow timing only if you want Gaia to use it."
        case .stepCount:
            return "Activity volume context for daily recovery patterns."
        }
    }

    static let defaultSelection: Set<String> = Set(allCases.map(\.rawValue))
    static let defaultStorageValue: String = allCases.map(\.rawValue).sorted().joined(separator: ",")
}

struct UserExperienceProfile: Codable, Equatable {
    var mode: ExperienceMode = .scientific
    var guide: GuideType = .cat
    var tone: ToneStyle = .balanced
    var tempUnit: TemperatureUnit = .localeDefault
    var trackedStatKeys: [TrackedStatKey] = TrackedStatKey.defaultSelection
    var smartStatSwapEnabled: Bool = true
    var favoriteSymptomCodes: [String] = []
    var lunarSensitivityDeclared: Bool = false
    var onboardingStep: OnboardingStep = .welcome
    var onboardingCompleted: Bool = false
    var onboardingCompletedAt: String?
    var healthkitRequestedAt: String?
    var lastBackfillAt: String?

    init() {}

    private enum CodingKeys: String, CodingKey {
        case mode
        case guide
        case tone
        case tempUnit
        case trackedStatKeys
        case smartStatSwapEnabled
        case favoriteSymptomCodes
        case lunarSensitivityDeclared
        case onboardingStep
        case onboardingCompleted
        case onboardingCompletedAt
        case healthkitRequestedAt
        case lastBackfillAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        mode = try container.decodeIfPresent(ExperienceMode.self, forKey: .mode) ?? .scientific
        guide = try container.decodeIfPresent(GuideType.self, forKey: .guide) ?? .cat
        tone = try container.decodeIfPresent(ToneStyle.self, forKey: .tone) ?? .balanced
        tempUnit = try container.decodeIfPresent(TemperatureUnit.self, forKey: .tempUnit) ?? .localeDefault
        trackedStatKeys = try container.decodeIfPresent([TrackedStatKey].self, forKey: .trackedStatKeys) ?? TrackedStatKey.defaultSelection
        smartStatSwapEnabled = try container.decodeIfPresent(Bool.self, forKey: .smartStatSwapEnabled) ?? true
        favoriteSymptomCodes = Self.normalizeFavoriteSymptomCodes(
            try container.decodeIfPresent([String].self, forKey: .favoriteSymptomCodes) ?? []
        )
        lunarSensitivityDeclared = try container.decodeIfPresent(Bool.self, forKey: .lunarSensitivityDeclared) ?? false
        onboardingStep = try container.decodeIfPresent(OnboardingStep.self, forKey: .onboardingStep) ?? .welcome
        onboardingCompleted = try container.decodeIfPresent(Bool.self, forKey: .onboardingCompleted) ?? false
        onboardingCompletedAt = try container.decodeIfPresent(String.self, forKey: .onboardingCompletedAt)
        healthkitRequestedAt = try container.decodeIfPresent(String.self, forKey: .healthkitRequestedAt)
        lastBackfillAt = try container.decodeIfPresent(String.self, forKey: .lastBackfillAt)
    }

    private static func normalizeFavoriteSymptomCodes(_ codes: [String]) -> [String] {
        var normalized: [String] = []
        for code in codes {
            let token = normalize(code)
            if token.isEmpty || normalized.contains(token) {
                continue
            }
            normalized.append(token)
            if normalized.count >= FavoriteSymptomPreference.maxCount {
                break
            }
        }
        return normalized
    }

    static let `default` = UserExperienceProfile()
}

struct UserExperienceProfileEnvelope: Codable {
    let ok: Bool?
    let preferences: UserExperienceProfile?
    let error: String?
    let detail: String?
}

struct DeleteAccountResult: Decodable {
    let deletedUserId: String?
    let rowsDeleted: Int?
    let tablesTouched: Int?
}

struct DeleteAccountPreflightTableCount: Decodable {
    let table: String
    let rows: Int
}

struct DeleteAccountPreflightResult: Decodable {
    let userId: String?
    let deleteReady: Bool?
    let authDeleteReady: Bool?
    let rowsFound: Int?
    let tablesWithRows: Int?
    let largestTables: [DeleteAccountPreflightTableCount]?
    let issues: [String]?
}

struct BugReportResult: Decodable {
    let reportId: String?
    let createdAt: Date?
    let alertSent: Bool?
    let alertError: String?
    let alertEmailTo: String?
}

struct UserExperienceProfileUpdate: Encodable {
    var mode: ExperienceMode? = nil
    var guide: GuideType? = nil
    var tone: ToneStyle? = nil
    var tempUnit: TemperatureUnit? = nil
    var trackedStatKeys: [TrackedStatKey]? = nil
    var smartStatSwapEnabled: Bool? = nil
    var favoriteSymptomCodes: [String]? = nil
    var lunarSensitivityDeclared: Bool? = nil
    var onboardingStep: OnboardingStep? = nil
    var onboardingCompleted: Bool? = nil
    var healthkitRequested: Bool? = nil
    var lastBackfillAt: String? = nil

    private enum CodingKeys: String, CodingKey {
        case mode
        case guide
        case tone
        case tempUnit = "temp_unit"
        case trackedStatKeys = "tracked_stat_keys"
        case smartStatSwapEnabled = "smart_stat_swap_enabled"
        case favoriteSymptomCodes = "favorite_symptom_codes"
        case lunarSensitivityDeclared = "lunar_sensitivity_declared"
        case onboardingStep = "onboarding_step"
        case onboardingCompleted = "onboarding_completed"
        case healthkitRequested = "healthkit_requested"
        case lastBackfillAt = "last_backfill_at"
    }
}

enum MembershipPlan: String {
    case free
    case plus
    case pro

    var title: String {
        switch self {
        case .free:
            return "Free"
        case .plus:
            return "Plus"
        case .pro:
            return "Pro"
        }
    }
}
