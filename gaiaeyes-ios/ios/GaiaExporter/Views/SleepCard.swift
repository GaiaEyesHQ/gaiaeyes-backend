//
//  SleepCard.swift
//  GaiaExporter
//
//  Created by Jennifer O'Brien on 9/20/25.
//


import SwiftUI

/// Sleep summary card showing total minutes, efficiency, and stage breakdown.
struct SleepCard: View {
    let title: String
    let totalMin: Int
    let remMin: Int?
    let coreMin: Int?
    let deepMin: Int?
    let awakeMin: Int?
    let inbedMin: Int?
    let efficiency: Double? // 0..1

    private var efficiencyPercentText: String? {
        guard let e = efficiency, e.isFinite else { return nil }
        return "\(Int((e * 100).rounded()))%"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(title)
                    .font(.headline)
                Spacer()
                if let pct = efficiencyPercentText {
                    Text(pct)
                        .font(.subheadline).bold()
                        .padding(.horizontal, 8).padding(.vertical, 4)
                        .background(Color(.secondarySystemBackground))
                        .cornerRadius(8)
                        .accessibilityLabel("Sleep efficiency")
                        .accessibilityValue(pct)
                }
            }

            let hours = totalMin / 60
            let mins  = totalMin % 60
            Text("\(hours)h \(mins)m total")
                .font(.title2).bold()

            // Stage breakdown chips
            HStack(spacing: 8) {
                if let r = remMin, r > 0 { TagView(label: "REM", value: r) }
                if let c = coreMin, c > 0 { TagView(label: "Core", value: c) }
                if let d = deepMin, d > 0 { TagView(label: "Deep", value: d) }
                if let a = awakeMin, a > 0 { TagView(label: "Awake", value: a) }
                if let ib = inbedMin, ib > 0 { TagView(label: "In bed", value: ib) }
            }
        }
        .padding()
        .background(.ultraThinMaterial)
        .cornerRadius(16)
    }
}

private struct TagView: View {
    let label: String
    let value: Int
    var body: some View {
        HStack(spacing: 6) {
            Text(label).font(.caption).foregroundColor(.secondary)
            Text("\(value)m").font(.caption).bold()
        }
        .padding(.horizontal, 8).padding(.vertical, 6)
        .background(Color(.secondarySystemBackground))
        .cornerRadius(8)
    }
}
