import Foundation

final class StatusStore {
    private let lock = NSLock()
    static let shared = StatusStore()
    private let ud = UserDefaults.standard

    // Keys
    private func key(_ k: String) -> String { "status.\(k)" }
    private func uploadKey(for type: String) -> String { key("lastUpload.\(type)") }
    private var bgRunKey: String { key("lastBackgroundRun") }

    // Generic keys for throttling / last-run tracking
    private func lastRunKey(_ name: String) -> String { key("lastRun.\(name)") }

    // MARK: - Generic last-run helpers
    func setLastRun(named name: String, date: Date = Date()) {
        lock.lock(); defer { lock.unlock() }
        ud.set(date.timeIntervalSince1970, forKey: lastRunKey(name))
    }

    func lastRun(named name: String) -> Date? {
        lock.lock(); defer { lock.unlock() }
        let t = ud.double(forKey: lastRunKey(name))
        return t > 0 ? Date(timeIntervalSince1970: t) : nil
    }

    /// Returns true if the named action should be throttled because it ran less than `interval` seconds ago.
    func shouldThrottle(named name: String, within interval: TimeInterval) -> Bool {
        lock.lock(); defer { lock.unlock() }
        let now = Date().timeIntervalSince1970
        let t = ud.double(forKey: lastRunKey(name))
        guard t > 0 else { return false }
        return (now - t) < interval
    }

    /// Marks the named action as just run and returns whether it was allowed (not throttled).
    /// If the previous run is within `interval`, returns false and does not update the timestamp.
    @discardableResult
    func tryMarkRun(named name: String, minInterval: TimeInterval) -> Bool {
        lock.lock(); defer { lock.unlock() }
        let now = Date().timeIntervalSince1970
        let t = ud.double(forKey: lastRunKey(name))
        if t > 0, (now - t) < minInterval { return false }
        ud.set(now, forKey: lastRunKey(name))
        return true
    }

    /// Runs `block` only if the named action is due (last run older than `minInterval`). Returns whether it executed.
    @discardableResult
    func runIfDue(named name: String, minInterval: TimeInterval, _ block: () -> Void) -> Bool {
        if tryMarkRun(named: name, minInterval: minInterval) {
            block()
            return true
        }
        return false
    }

    /// Async variant for suspending work.
    @discardableResult
    func runIfDueAsync(named name: String, minInterval: TimeInterval, _ block: @escaping () async -> Void) async -> Bool {
        if tryMarkRun(named: name, minInterval: minInterval) {
            await block()
            return true
        }
        return false
    }

    // Setters
    func setUpload(for type: String, date: Date = Date()) {
        ud.set(date.timeIntervalSince1970, forKey: uploadKey(for: type))
    }
    func setBackgroundRun(_ date: Date = Date()) {
        ud.set(date.timeIntervalSince1970, forKey: bgRunKey)
    }

    // Getters
    func lastUpload(for type: String) -> Date? {
        let t = ud.double(forKey: uploadKey(for: type))
        return t > 0 ? Date(timeIntervalSince1970: t) : nil
    }
    func lastBackgroundRun() -> Date? {
        let t = ud.double(forKey: bgRunKey)
        return t > 0 ? Date(timeIntervalSince1970: t) : nil
    }
}//
//  StatusStore.swift
//  GaiaExporter
//
//  Created by Jennifer O'Brien on 9/2/25.
//

