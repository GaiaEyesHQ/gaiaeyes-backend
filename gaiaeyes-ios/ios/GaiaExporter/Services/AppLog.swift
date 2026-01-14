//
//  AppLog.swift
//  GaiaExporter
//
//  Created by Jennifer O'Brien on 9/19/25.
//
import Foundation

extension Notification.Name {
    static let AppLogLine = Notification.Name("AppLogLine")
}

/// Send a log line to both Xcode console and the in-app log panel.
@inline(__always)
func appLog(_ line: String) {
    // Still show in Xcode console
    print(line)
    // Also notify ContentView (and anything else observing)
    NotificationCenter.default.post(name: .AppLogLine, object: line)
}
