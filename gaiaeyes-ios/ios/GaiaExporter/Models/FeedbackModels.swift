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

    private enum CodingKeys: String, CodingKey {
        case id
        case day
        case phase
        case questionText
        case scheduledFor
        case deliveredAt
        case activeSymptomLabels
        case recentSymptomCodes
        case painLoggedRecently
        case energyLoggedRecently
        case moodLoggedRecently
        case sleepLoggedRecently
        case suggestedPainTypes
        case suggestedEnergyDetails
        case suggestedMoodTypes
        case suggestedSleepImpacts
        case pushDeliveryEnabled
        case status
    }

    init(
        id: String,
        day: String,
        phase: String? = nil,
        questionText: String,
        scheduledFor: String? = nil,
        deliveredAt: String? = nil,
        activeSymptomLabels: [String] = [],
        recentSymptomCodes: [String] = [],
        painLoggedRecently: Bool = false,
        energyLoggedRecently: Bool = false,
        moodLoggedRecently: Bool = false,
        sleepLoggedRecently: Bool = false,
        suggestedPainTypes: [String] = [],
        suggestedEnergyDetails: [String] = [],
        suggestedMoodTypes: [String] = [],
        suggestedSleepImpacts: [String] = [],
        pushDeliveryEnabled: Bool = false,
        status: String? = nil
    ) {
        self.id = id
        self.day = day
        self.phase = phase
        self.questionText = questionText
        self.scheduledFor = scheduledFor
        self.deliveredAt = deliveredAt
        self.activeSymptomLabels = activeSymptomLabels
        self.recentSymptomCodes = recentSymptomCodes
        self.painLoggedRecently = painLoggedRecently
        self.energyLoggedRecently = energyLoggedRecently
        self.moodLoggedRecently = moodLoggedRecently
        self.sleepLoggedRecently = sleepLoggedRecently
        self.suggestedPainTypes = suggestedPainTypes
        self.suggestedEnergyDetails = suggestedEnergyDetails
        self.suggestedMoodTypes = suggestedMoodTypes
        self.suggestedSleepImpacts = suggestedSleepImpacts
        self.pushDeliveryEnabled = pushDeliveryEnabled
        self.status = status
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? ""
        day = try container.decodeIfPresent(String.self, forKey: .day) ?? ""
        phase = try container.decodeIfPresent(String.self, forKey: .phase)
        questionText = try container.decodeIfPresent(String.self, forKey: .questionText) ?? "How did today feel?"
        scheduledFor = try container.decodeIfPresent(String.self, forKey: .scheduledFor)
        deliveredAt = try container.decodeIfPresent(String.self, forKey: .deliveredAt)
        activeSymptomLabels = try container.decodeIfPresent([String].self, forKey: .activeSymptomLabels) ?? []
        recentSymptomCodes = try container.decodeIfPresent([String].self, forKey: .recentSymptomCodes) ?? []
        painLoggedRecently = try container.decodeIfPresent(Bool.self, forKey: .painLoggedRecently) ?? false
        energyLoggedRecently = try container.decodeIfPresent(Bool.self, forKey: .energyLoggedRecently) ?? false
        moodLoggedRecently = try container.decodeIfPresent(Bool.self, forKey: .moodLoggedRecently) ?? false
        sleepLoggedRecently = try container.decodeIfPresent(Bool.self, forKey: .sleepLoggedRecently) ?? false
        suggestedPainTypes = try container.decodeIfPresent([String].self, forKey: .suggestedPainTypes) ?? []
        suggestedEnergyDetails = try container.decodeIfPresent([String].self, forKey: .suggestedEnergyDetails) ?? []
        suggestedMoodTypes = try container.decodeIfPresent([String].self, forKey: .suggestedMoodTypes) ?? []
        suggestedSleepImpacts = try container.decodeIfPresent([String].self, forKey: .suggestedSleepImpacts) ?? []
        pushDeliveryEnabled = try container.decodeIfPresent(Bool.self, forKey: .pushDeliveryEnabled) ?? false
        status = try container.decodeIfPresent(String.self, forKey: .status)
    }
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
    let exposures: [String]

    private enum CodingKeys: String, CodingKey {
        case day
        case promptId
        case comparedToYesterday
        case energyLevel
        case usableEnergy
        case systemLoad
        case painLevel
        case painType
        case energyDetail
        case moodLevel
        case moodType
        case sleepImpact
        case predictionMatch
        case noteText
        case completedAt
        case exposures
    }

    init(
        day: String,
        promptId: String? = nil,
        comparedToYesterday: String,
        energyLevel: String,
        usableEnergy: String,
        systemLoad: String,
        painLevel: String,
        painType: String? = nil,
        energyDetail: String? = nil,
        moodLevel: String,
        moodType: String? = nil,
        sleepImpact: String? = nil,
        predictionMatch: String? = nil,
        noteText: String? = nil,
        completedAt: String? = nil,
        exposures: [String] = []
    ) {
        self.day = day
        self.promptId = promptId
        self.comparedToYesterday = comparedToYesterday
        self.energyLevel = energyLevel
        self.usableEnergy = usableEnergy
        self.systemLoad = systemLoad
        self.painLevel = painLevel
        self.painType = painType
        self.energyDetail = energyDetail
        self.moodLevel = moodLevel
        self.moodType = moodType
        self.sleepImpact = sleepImpact
        self.predictionMatch = predictionMatch
        self.noteText = noteText
        self.completedAt = completedAt
        self.exposures = exposures
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        day = try container.decodeIfPresent(String.self, forKey: .day) ?? ""
        promptId = try container.decodeIfPresent(String.self, forKey: .promptId)
        comparedToYesterday = try container.decodeIfPresent(String.self, forKey: .comparedToYesterday) ?? ""
        energyLevel = try container.decodeIfPresent(String.self, forKey: .energyLevel) ?? ""
        usableEnergy = try container.decodeIfPresent(String.self, forKey: .usableEnergy) ?? ""
        systemLoad = try container.decodeIfPresent(String.self, forKey: .systemLoad) ?? ""
        painLevel = try container.decodeIfPresent(String.self, forKey: .painLevel) ?? ""
        painType = try container.decodeIfPresent(String.self, forKey: .painType)
        energyDetail = try container.decodeIfPresent(String.self, forKey: .energyDetail)
        moodLevel = try container.decodeIfPresent(String.self, forKey: .moodLevel) ?? ""
        moodType = try container.decodeIfPresent(String.self, forKey: .moodType)
        sleepImpact = try container.decodeIfPresent(String.self, forKey: .sleepImpact)
        predictionMatch = try container.decodeIfPresent(String.self, forKey: .predictionMatch)
        noteText = try container.decodeIfPresent(String.self, forKey: .noteText)
        completedAt = try container.decodeIfPresent(String.self, forKey: .completedAt)
        exposures = try container.decodeIfPresent([String].self, forKey: .exposures) ?? []
    }
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

    private enum CodingKeys: String, CodingKey {
        case windowDays
        case totalCheckins
        case mostlyRight
        case partlyRight
        case notReally
        case matchRate
        case resolvedCount
        case improvingCount
        case worseCount
    }

    init(
        windowDays: Int,
        totalCheckins: Int,
        mostlyRight: Int,
        partlyRight: Int,
        notReally: Int,
        matchRate: Double?,
        resolvedCount: Int,
        improvingCount: Int,
        worseCount: Int
    ) {
        self.windowDays = windowDays
        self.totalCheckins = totalCheckins
        self.mostlyRight = mostlyRight
        self.partlyRight = partlyRight
        self.notReally = notReally
        self.matchRate = matchRate
        self.resolvedCount = resolvedCount
        self.improvingCount = improvingCount
        self.worseCount = worseCount
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        windowDays = try container.decodeIfPresent(Int.self, forKey: .windowDays) ?? 21
        totalCheckins = try container.decodeIfPresent(Int.self, forKey: .totalCheckins) ?? 0
        mostlyRight = try container.decodeIfPresent(Int.self, forKey: .mostlyRight) ?? 0
        partlyRight = try container.decodeIfPresent(Int.self, forKey: .partlyRight) ?? 0
        notReally = try container.decodeIfPresent(Int.self, forKey: .notReally) ?? 0
        matchRate = try container.decodeIfPresent(Double.self, forKey: .matchRate)
        resolvedCount = try container.decodeIfPresent(Int.self, forKey: .resolvedCount) ?? 0
        improvingCount = try container.decodeIfPresent(Int.self, forKey: .improvingCount) ?? 0
        worseCount = try container.decodeIfPresent(Int.self, forKey: .worseCount) ?? 0
    }
}

struct DailyCheckInSettings: Decodable, Hashable {
    let enabled: Bool
    let pushEnabled: Bool
    let cadence: String
    let reminderTime: String

    private enum CodingKeys: String, CodingKey {
        case enabled
        case pushEnabled
        case cadence
        case reminderTime
    }

    init(
        enabled: Bool,
        pushEnabled: Bool,
        cadence: String,
        reminderTime: String
    ) {
        self.enabled = enabled
        self.pushEnabled = pushEnabled
        self.cadence = cadence
        self.reminderTime = reminderTime
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        enabled = try container.decodeIfPresent(Bool.self, forKey: .enabled) ?? false
        pushEnabled = try container.decodeIfPresent(Bool.self, forKey: .pushEnabled) ?? false
        cadence = try container.decodeIfPresent(String.self, forKey: .cadence) ?? "balanced"
        reminderTime = try container.decodeIfPresent(String.self, forKey: .reminderTime) ?? "20:00"
    }
}

struct DailyCheckInStatus: Decodable, Hashable {
    let prompt: DailyCheckInPrompt?
    let latestEntry: DailyCheckInEntry?
    let targetDay: String?
    let calibrationSummary: FeedbackCalibrationSummary
    let settings: DailyCheckInSettings

    private enum CodingKeys: String, CodingKey {
        case prompt
        case latestEntry
        case targetDay
        case calibrationSummary
        case settings
    }

    init(
        prompt: DailyCheckInPrompt? = nil,
        latestEntry: DailyCheckInEntry? = nil,
        targetDay: String? = nil,
        calibrationSummary: FeedbackCalibrationSummary,
        settings: DailyCheckInSettings
    ) {
        self.prompt = prompt
        self.latestEntry = latestEntry
        self.targetDay = targetDay
        self.calibrationSummary = calibrationSummary
        self.settings = settings
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        prompt = try container.decodeIfPresent(DailyCheckInPrompt.self, forKey: .prompt)
        latestEntry = try container.decodeIfPresent(DailyCheckInEntry.self, forKey: .latestEntry)
        targetDay = try container.decodeIfPresent(String.self, forKey: .targetDay)
        calibrationSummary = try container.decodeIfPresent(FeedbackCalibrationSummary.self, forKey: .calibrationSummary)
            ?? FeedbackCalibrationSummary(windowDays: 21, totalCheckins: 0, mostlyRight: 0, partlyRight: 0, notReally: 0, matchRate: nil, resolvedCount: 0, improvingCount: 0, worseCount: 0)
        settings = try container.decodeIfPresent(DailyCheckInSettings.self, forKey: .settings)
            ?? DailyCheckInSettings(enabled: false, pushEnabled: false, cadence: "balanced", reminderTime: "20:00")
    }
}

extension DailyCheckInEntry {
    private static let illnessDetailLabels: [String: String] = [
        "illness_respiratory": "Sinus / respiratory",
        "illness_gastrointestinal": "Stomach / GI",
        "illness_fever": "Fever / infection",
        "illness_other": "Other / unsure",
    ]

    static func summaryExposureLabel(for exposureID: String) -> String? {
        switch exposureID.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "overexertion":
            return "Heavy activity"
        case "allergen_exposure":
            return "Allergen exposure"
        case "temporary_illness":
            return "Temporary illness"
        case let value where Self.illnessDetailLabels[value] != nil:
            return Self.illnessDetailLabels[value]
        case "":
            return nil
        default:
            return exposureID
                .replacingOccurrences(of: "_", with: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .capitalized
        }
    }

    static func summaryExposureText(for exposureIDs: [String]) -> String? {
        var labels: [String] = []
        var seen: Set<String> = []
        let normalizedIDs = Set(exposureIDs.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() })
        if normalizedIDs.contains("temporary_illness") {
            let details = Self.illnessDetailLabels
                .filter { normalizedIDs.contains($0.key) }
                .map(\.value)
                .sorted()
            let label = details.isEmpty ? "Temporary illness" : "Temporary illness: \(details.joined(separator: ", "))"
            labels.append(label)
            seen.insert("temporary illness")
        }
        for exposureID in exposureIDs where !Self.illnessDetailLabels.keys.contains(exposureID.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()) {
            guard let label = summaryExposureLabel(for: exposureID), !label.isEmpty else { continue }
            let normalized = label.lowercased()
            if seen.insert(normalized).inserted {
                labels.append(label)
            }
        }
        guard !labels.isEmpty else { return nil }
        return labels.joined(separator: ", ")
    }

    var summaryExposureText: String? {
        Self.summaryExposureText(for: exposures)
    }
}
