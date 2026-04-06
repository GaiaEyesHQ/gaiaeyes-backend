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

    private struct StageStat: Identifiable {
        let id: String
        let label: String
        let minutes: Int
        let progress: Double
        let tint: Color
    }

    private struct StageTile: View {
        let stat: StageStat

        var body: some View {
            VStack(alignment: .leading, spacing: 8) {
                Text(stat.label.uppercased())
                    .font(.caption2.weight(.semibold))
                    .foregroundColor(.secondary)
                Text("\(stat.minutes)m")
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                    .minimumScaleFactor(0.85)
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule()
                            .fill(Color.white.opacity(0.08))
                        Capsule()
                            .fill(stat.tint.opacity(0.72))
                            .frame(width: max(12, geo.size.width * stat.progress))
                    }
                }
                .frame(height: 8)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(Color.black.opacity(0.20))
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(stat.tint.opacity(0.22), lineWidth: 1)
            )
        }
    }

    private var stageStats: [StageStat] {
        let reference = Double(max(inbedMin ?? totalMin, totalMin, 1))
        var stats: [StageStat] = []

        if let remMin, remMin > 0 {
            stats.append(StageStat(id: "rem", label: "REM", minutes: remMin, progress: min(max(Double(remMin) / reference, 0.12), 1.0), tint: Color(red: 0.49, green: 0.75, blue: 0.66)))
        }
        if let coreMin, coreMin > 0 {
            stats.append(StageStat(id: "core", label: "Core", minutes: coreMin, progress: min(max(Double(coreMin) / reference, 0.12), 1.0), tint: Color(red: 0.68, green: 0.73, blue: 0.43)))
        }
        if let deepMin, deepMin > 0 {
            stats.append(StageStat(id: "deep", label: "Deep", minutes: deepMin, progress: min(max(Double(deepMin) / reference, 0.12), 1.0), tint: Color(red: 0.86, green: 0.75, blue: 0.49)))
        }
        if let awakeMin, awakeMin > 0 {
            stats.append(StageStat(id: "awake", label: "Awake", minutes: awakeMin, progress: min(max(Double(awakeMin) / reference, 0.12), 1.0), tint: Color(red: 0.83, green: 0.58, blue: 0.51)))
        }
        if let inbedMin, inbedMin > 0 {
            stats.append(StageStat(id: "inbed", label: "In bed", minutes: inbedMin, progress: min(max(Double(inbedMin) / reference, 0.12), 1.0), tint: Color.white.opacity(0.68)))
        }

        return stats
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Text(title)
                    .font(.headline)
                Spacer()
                if let pct = efficiencyPercentText {
                    Text(pct)
                        .font(.subheadline.bold())
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.black.opacity(0.20))
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(Color.white.opacity(0.10), lineWidth: 1)
                        )
                        .accessibilityLabel("Sleep efficiency")
                        .accessibilityValue(pct)
                }
            }

            let hours = totalMin / 60
            let mins  = totalMin % 60
            Text("\(hours)h \(mins)m total")
                .font(.title2.bold())

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 68), spacing: 8)],
                spacing: 8
            ) {
                ForEach(stageStats) { stat in
                    StageTile(stat: stat)
                }
            }
        }
        .padding(16)
        .background(Color.white.opacity(0.06))
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(Color.white.opacity(0.08), lineWidth: 1)
        )
    }
}
