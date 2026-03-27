import Foundation

struct SymptomFollowUpResult: Decodable, Hashable {
    let prompt: CurrentSymptomFollowUpPrompt
    let episode: CurrentSymptomItem
}

struct DailyCheckInPrompt: Decodable, Identifiable, Hashable {
    let id: String
    let day: String
    let phase: String?
    let questionText: String
    let scheduledFor: String?
    let deliveredAt: String?
    let activeSymptomLabels: [String]
    let recentSymptomCodes: [String]
    let painLoggedRecently: Bool
    let energyLoggedRecently: Bool
    let moodLoggedRecently: Bool
    let sleepLoggedRecently: Bool
    let suggestedPainTypes: [String]
    let suggestedEnergyDetails: [String]
    let suggestedMoodTypes: [String]
    let suggestedSleepImpacts: [String]
    let pushDeliveryEnabled: Bool
    let status: String?
}

struct DailyCheckInEntry: Decodable, Hashable {
    let day: String
    let promptId: String?
    let comparedToYesterday: String
    let energyLevel: String
    let usableEnergy: String
    let systemLoad: String
    let painLevel: String
    let painType: String?
    let energyDetail: String?
    let moodLevel: String
    let moodType: String?
    let sleepImpact: String?
    let predictionMatch: String?
    let noteText: String?
    let completedAt: String?
}

struct FeedbackCalibrationSummary: Decodable, Hashable {
    let windowDays: Int
    let totalCheckins: Int
    let mostlyRight: Int
    let partlyRight: Int
    let notReally: Int
    let matchRate: Double?
    let resolvedCount: Int
    let improvingCount: Int
    let worseCount: Int
}

struct DailyCheckInSettings: Decodable, Hashable {
    let enabled: Bool
    let pushEnabled: Bool
    let cadence: String
    let reminderTime: String
}

struct DailyCheckInStatus: Decodable, Hashable {
    let prompt: DailyCheckInPrompt?
    let latestEntry: DailyCheckInEntry?
    let calibrationSummary: FeedbackCalibrationSummary
    let settings: DailyCheckInSettings
}
