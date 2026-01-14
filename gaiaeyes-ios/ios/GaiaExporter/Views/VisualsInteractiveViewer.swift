import SwiftUI
import AVKit
import Charts

struct OverlaySeries: Identifiable, Hashable {
    let id = UUID()
    let name: String
    let unit: String?
    let points: [OverlayPoint]

    struct OverlayPoint: Identifiable, Hashable {
        let id = UUID()
        let date: Date
        let value: Double
    }
}

struct VisualsInteractiveViewer: View {
    let item: SpaceVisualItem
    let baseURL: URL?
    let overlaySeries: [OverlaySeries]
    var onClose: (() -> Void)? = nil

    @State private var zoom: CGFloat = 1.0
    @State private var selectedDate: Date? = nil
    @State private var hiddenSeries: Set<UUID> = []
    @State private var isFullScreen: Bool = false
    @State private var player: AVPlayer? = nil

    private var resolvedURL: URL? {
        guard let raw = item.url?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else { return nil }
        if let u = URL(string: raw), u.scheme != nil { return u }
        guard let baseURL else { return URL(string: raw) }
        return URL(string: raw.hasPrefix("/") ? String(raw.dropFirst()) : raw, relativeTo: baseURL)
    }

    private var isVideo: Bool {
        resolvedURL?.absoluteString.lowercased().contains(".mp4") ?? false
    }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.title ?? "Visual")
                        .font(.headline)
                    if let credit = item.credit, !credit.isEmpty {
                        Text(credit)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                Spacer()
                if resolvedURL != nil {
                    Button(action: { isFullScreen = true }) {
                        Image(systemName: "arrow.up.left.and.arrow.down.right")
                    }
                    .buttonStyle(.borderless)
                }
                if let onClose {
                    Button(action: onClose) { Image(systemName: "xmark.circle.fill") }
                        .buttonStyle(.borderless)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal)

            GeometryReader { proxy in
                ZStack {
                    Rectangle().fill(.black.opacity(0.05))
                    if let url = resolvedURL {
                        if isVideo {
                            VideoPlayer(player: player)
                                .onAppear {
                                    if player == nil { player = AVPlayer(url: url) }
                                    player?.play()
                                }
                                .onDisappear {
                                    player?.pause()
                                    player = nil
                                }
                                .scaleEffect(zoom)
                                .gesture(MagnificationGesture().onChanged { zoom = max(1.0, $0) })
                                .onTapGesture {
                                    if let p = player {
                                        if p.timeControlStatus == .playing { p.pause() } else { p.play() }
                                    }
                                }
                        } else {
                            AsyncImage(url: url) { phase in
                                switch phase {
                                case .empty:
                                    ProgressView()
                                case .success(let image):
                                    image
                                        .resizable()
                                        .scaledToFit()
                                        .scaleEffect(zoom)
                                        .gesture(MagnificationGesture().onChanged { zoom = max(1.0, $0) })
                                        .highPriorityGesture(
                                            TapGesture(count: 2).onEnded {
                                                zoom = (abs(zoom - 1.0) < 0.01) ? 2.0 : 1.0
                                            }
                                        )
                                        .onTapGesture {
                                            isFullScreen = true
                                        }
                                case .failure:
                                    Image(systemName: "exclamationmark.triangle.fill").foregroundColor(.orange)
                                @unknown default:
                                    EmptyView()
                                }
                            }
                        }
                    } else {
                        Text("Unable to load visual")
                            .foregroundColor(.secondary)
                    }
                }
                .frame(width: proxy.size.width, height: proxy.size.height)
                .contentShape(Rectangle())
            }
            .frame(height: 320)

            if let url = resolvedURL {
                FullScreenLauncher(isPresented: $isFullScreen, url: url, title: item.title, credit: item.credit, isVideo: isVideo)
            }

            if !overlaySeries.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Overlays")
                        .font(.headline)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack {
                            ForEach(overlaySeries) { series in
                                let hidden = hiddenSeries.contains(series.id)
                                Button {
                                    if hidden { hiddenSeries.remove(series.id) } else { hiddenSeries.insert(series.id) }
                                } label: {
                                    HStack {
                                        Circle()
                                            .fill(hidden ? Color.gray.opacity(0.4) : .accentColor)
                                            .frame(width: 10, height: 10)
                                        Text(series.name)
                                    }
                                    .padding(8)
                                    .background(.thinMaterial, in: Capsule())
                                }
                            }
                        }
                    }

                    Chart {
                        ForEach(overlaySeries) { series in
                            if !hiddenSeries.contains(series.id) {
                                ForEach(series.points) { pt in
                                    LineMark(
                                        x: .value("Time", pt.date),
                                        y: .value(series.unit ?? "Value", pt.value)
                                    )
                                    .foregroundStyle(by: .value("Series", series.name))
                                    .interpolationMethod(.catmullRom)
                                }
                            }
                        }
                        if let selectedDate {
                            RuleMark(x: .value("Selected", selectedDate))
                                .foregroundStyle(Color.secondary)
                                .lineStyle(StrokeStyle(lineWidth: 1, dash: [4]))
                        }
                    }
                    .frame(height: 180)

                    if let latest = overlaySeries.flatMap({ $0.points }).max(by: { $0.date < $1.date })?.date {
                        Slider(value: Binding(get: {
                            selectedDate?.timeIntervalSince1970 ?? latest.timeIntervalSince1970
                        }, set: { newVal in
                            selectedDate = Date(timeIntervalSince1970: newVal)
                        }), in: overlayRange)
                        .padding(.horizontal, 4)
                    }
                }
                .padding(.horizontal)
            }
        }
        .padding(.vertical)
    }

    private var overlayRange: ClosedRange<Double> {
        let all = overlaySeries.flatMap { $0.points.map { $0.date.timeIntervalSince1970 } }
        guard let min = all.min(), let max = all.max(), min < max else { return 0...1 }
        return min...max
    }
}

private struct FullScreenLauncher: View {
    @Binding var isPresented: Bool
    let url: URL
    let title: String?
    let credit: String?
    let isVideo: Bool

    var body: some View {
        EmptyView()
            .fullScreenCover(isPresented: $isPresented) {
                FullscreenVisualView(url: url, title: title, credit: credit, isVideo: isVideo)
            }
    }
}

private struct FullscreenVisualView: View {
    let url: URL
    let title: String?
    let credit: String?
    let isVideo: Bool

    @Environment(\.dismiss) private var dismiss
    @State private var zoom: CGFloat = 1.0
    @State private var player: AVPlayer? = nil

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            Group {
                if isVideo {
                    VideoPlayer(player: player)
                        .onAppear {
                            if player == nil { player = AVPlayer(url: url) }
                            player?.play()
                        }
                        .onDisappear {
                            player?.pause()
                            player = nil
                        }
                        .scaleEffect(zoom)
                        .gesture(MagnificationGesture().onChanged { zoom = max(1.0, $0) })
                        .onTapGesture {
                            if let p = player {
                                if p.timeControlStatus == .playing { p.pause() } else { p.play() }
                            }
                        }
                } else {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .empty:
                            ProgressView()
                        case .success(let image):
                            image
                                .resizable()
                                .scaledToFit()
                                .scaleEffect(zoom)
                                .gesture(MagnificationGesture().onChanged { zoom = max(1.0, $0) })
                                .highPriorityGesture(
                                    TapGesture(count: 2).onEnded {
                                        zoom = (abs(zoom - 1.0) < 0.01) ? 2.0 : 1.0
                                    }
                                )
                        case .failure:
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundColor(.orange)
                        @unknown default:
                            EmptyView()
                        }
                    }
                }
            }
            .padding()
            .ignoresSafeArea()

            VStack {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title ?? "Visual")
                            .font(.headline)
                            .foregroundColor(.white)
                        if let credit, !credit.isEmpty {
                            Text(credit).font(.caption).foregroundColor(.white.opacity(0.8))
                        }
                    }
                    Spacer()
                    Button {
                        dismiss()
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.title2)
                            .foregroundColor(.white)
                    }
                    .buttonStyle(.borderless)
                }
                .padding()
                Spacer()
            }
        }
    }
}
