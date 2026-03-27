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

enum OnboardingStep: String, CaseIterable, Codable, Identifiable {
    case welcome
    case mode
    case guide
    case tone
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
    var onboardingStep: OnboardingStep = .welcome
    var onboardingCompleted: Bool = false
    var onboardingCompletedAt: String?
    var healthkitRequestedAt: String?
    var lastBackfillAt: String?

    static let `default` = UserExperienceProfile()
}

struct UserExperienceProfileEnvelope: Codable {
    let ok: Bool?
    let preferences: UserExperienceProfile?
    let error: String?
    let detail: String?
}

struct UserExperienceProfileUpdate: Encodable {
    var mode: ExperienceMode? = nil
    var guide: GuideType? = nil
    var tone: ToneStyle? = nil
    var onboardingStep: OnboardingStep? = nil
    var onboardingCompleted: Bool? = nil
    var healthkitRequested: Bool? = nil
    var lastBackfillAt: String? = nil

    private enum CodingKeys: String, CodingKey {
        case mode
        case guide
        case tone
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
