import SwiftUI

struct FeaturesDiagnosticsPanel: View {
    let diag: Diagnostics
    let onCopyTrace: (() -> Void)?
    let onShareTrace: (() -> Void)?
    let onCopyToStatus: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            metaSection
            PresenceRow(title: "Initial Cache", map: diag.cacheSnapshotInitial)
            PresenceRow(title: "Final Cache", map: diag.cacheSnapshotFinal)
            PresenceRow(title: "Payload", map: diag.payloadSummary)
            cacheRefreshSection
            errorsSection
            traceSection
        }
    }

    private var metaSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 6) {
                metaRow(label: "Source", systemImage: "shippingbox", value: diag.source)
                metaRow(label: "Branch", systemImage: "person.text.rectangle", value: diag.branch)
                metaRow(label: "Day / Used", systemImage: "calendar", value: "\(diag.day ?? "-") / \(diag.dayUsed ?? "-")")
                metaRow(label: "TZ", systemImage: "globe", value: diag.tz)
            }
        } label: {
            Text("Meta")
        }
    }

    private func metaRow(label: String, systemImage: String, value: String?) -> some View {
        HStack {
            Label(label, systemImage: systemImage)
            Spacer()
            Text(value.flatMap { $0.isEmpty ? nil : $0 } ?? "-")
                .font(.footnote)
                .monospaced()
        }
    }

    private var cacheRefreshSection: some View {
        GroupBox {
            Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
                GridRow { Text("cache_hit"); bool(diag.cacheHit) }
                GridRow { Text("cache_fallback"); bool(diag.cacheFallback) }
                GridRow { Text("cache_rehydrated"); bool(diag.cacheRehydrated) }
                GridRow { Text("cache_updated"); bool(diag.cacheUpdated) }
                GridRow {
                    Text("cache_age_seconds")
                    Text(diag.cacheAgeSeconds.map { String(format: "%.1f", $0) } ?? "-")
                        .font(.footnote)
                        .monospaced()
                }
                Divider()
                GridRow { Text("refresh_attempted"); bool(diag.refreshAttempted) }
                GridRow { Text("refresh_scheduled"); bool(diag.refreshScheduled) }
                GridRow { Text("refresh_reason"); text(diag.refreshReason) }
                GridRow { Text("refresh_forced"); bool(diag.refreshForced) }
            }
            .font(.footnote)
        } label: {
            Text("Cache & Refresh")
        }
    }

    @ViewBuilder
    private var errorsSection: some View {
        if diag.lastError?.isEmpty == false || (diag.enrichmentErrors?.isEmpty == false) || diag.poolTimeout == true {
            GroupBox {
                VStack(alignment: .leading, spacing: 6) {
                    if let lastError = diag.lastError, !lastError.isEmpty {
                        Label("last_error", systemImage: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                        Text(lastError)
                            .font(.footnote)
                            .textSelection(.enabled)
                    }
                    if let list = diag.enrichmentErrors, !list.isEmpty {
                        Label("enrichment_errors", systemImage: "sensor.tag.radiowaves.forward")
                        ForEach(list, id: \.self) { err in
                            Text("• \(err)")
                                .font(.footnote)
                        }
                    }
                    if diag.poolTimeout == true {
                        Label("pool_timeout", systemImage: "tortoise.fill")
                            .foregroundColor(.orange)
                    }
                }
            } label: {
                Text("Errors")
            }
        }
    }

    private var traceSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Trace (latest first)")
                        .font(.subheadline)
                        .bold()
                    Spacer()
                    Button("Copy") { onCopyTrace?() }
                    Button("Share") { onShareTrace?() }
                    Button("Copy to Status") { onCopyToStatus?() }
                }
                let lines = (diag.trace ?? []).reversed()
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(lines.enumerated()), id: \.offset) { item in
                            Text(item.element)
                                .font(.caption)
                                .textSelection(.enabled)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(minHeight: 160, maxHeight: 260)
            }
        } label: {
            Text("Diagnostics Trace")
        }
    }

    @ViewBuilder
    private func bool(_ value: Bool?) -> some View {
        let isTrue = (value == true)
        Text(isTrue ? "true" : "false")
            .font(.footnote)
            .monospaced()
            .foregroundColor(isTrue ? .green : .secondary)
    }

    @ViewBuilder
    private func text(_ value: String?) -> some View {
        Text(value.flatMap { $0.isEmpty ? nil : $0 } ?? "-")
            .font(.footnote)
            .monospaced()
    }
}

private struct PresenceRow: View {
    let title: String
    let map: PresenceMap?

    var body: some View {
        GroupBox {
            HStack {
                Label(title, systemImage: "checkmark.seal")
                Spacer()
                Tag("health", map?.health)
                Tag("sleep", map?.sleep)
                Tag("space", map?.spaceWeather)
                Tag("sch", map?.schumann)
                Tag("post", map?.postCopy)
            }
        } label: {
            Text(title)
        }
    }
}

private struct Tag: View {
    let label: String
    let present: Bool?

    init(_ label: String, _ present: Bool?) {
        self.label = label
        self.present = present
    }

    var body: some View {
        Text(label)
            .font(.caption2)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background((present == true) ? Color.green.opacity(0.18) : Color.secondary.opacity(0.12))
            .foregroundColor((present == true) ? .green : .secondary)
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
    }
}
