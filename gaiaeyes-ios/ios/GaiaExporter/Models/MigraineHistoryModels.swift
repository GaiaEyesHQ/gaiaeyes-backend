import Foundation

enum MigraineCalendarFeature {
    static func resolve(isDebugBuild: Bool, arguments: [String]) -> Bool {
        isDebugBuild && arguments.contains("-gaia-enable-migraine-calendar")
    }
    static var isEnabled: Bool {
        resolve(isDebugBuild: _isDebugAssertConfiguration(), arguments: ProcessInfo.processInfo.arguments)
    }
}

struct MigraineHistoryEpisode: Decodable, Identifiable, Equatable {
    let id: String
    let startedAt: Date
    let endedAt: Date?
    let state: String
    let endStatus: String
    let severity: Int?
    let notePreview: String?

    func matches(_ interval: DateInterval, asOf: Date) -> Bool {
        guard startedAt < interval.end else { return false }
        if startedAt >= interval.start { return true }
        if endStatus == "recorded", let endedAt { return endedAt > interval.start }
        return endStatus == "open" && asOf > interval.start
    }
}

struct MigraineHistoryPage: Decodable {
    let items: [MigraineHistoryEpisode]
    let start: Date
    let end: Date
    let asOf: Date
    let snapshot: String
    let nextCursor: String?
    let complete: Bool
}

enum MigraineHistoryDates {
    static func calendar(timeZone: TimeZone) -> Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = .current
        calendar.timeZone = timeZone
        calendar.firstWeekday = Calendar.current.firstWeekday
        return calendar
    }
    static func month(containing date: Date, calendar: Calendar) -> DateInterval {
        calendar.dateInterval(of: .month, for: date)!
    }
    static func days(in month: DateInterval, calendar: Calendar) -> [Date] {
        let count = calendar.range(of: .day, in: .month, for: month.start)!.count
        return (0..<count).compactMap { calendar.date(byAdding: .day, value: $0, to: month.start) }
    }
}
