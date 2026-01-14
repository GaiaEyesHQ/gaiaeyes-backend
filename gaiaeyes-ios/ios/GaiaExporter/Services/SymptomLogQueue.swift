import Foundation

actor SymptomLogQueue {
    static let shared = SymptomLogQueue()

    private let storageKey = "gaia.symptom.queue"
    private var cached: [SymptomQueuedEvent] = []
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder

    private init() {
        encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        if let data = UserDefaults.standard.data(forKey: storageKey),
           let decoded = try? decoder.decode([SymptomQueuedEvent].self, from: data) {
            cached = decoded.map { $0.normalized() }
        }
    }

    private func persist() {
        if let data = try? encoder.encode(cached) {
            UserDefaults.standard.set(data, forKey: storageKey)
        }
    }

    func all() -> [SymptomQueuedEvent] { cached }

    func count() -> Int { cached.count }

    func enqueue(_ event: SymptomQueuedEvent) {
        cached.append(event.normalized())
        persist()
    }

    func remove(ids: Set<UUID>) {
        guard !ids.isEmpty else { return }
        cached.removeAll { ids.contains($0.id) }
        persist()
    }

    func replace(id: UUID, with event: SymptomQueuedEvent) {
        guard let index = cached.firstIndex(where: { $0.id == id }) else { return }
        cached[index] = event.normalized()
        persist()
    }

    func clear() {
        cached.removeAll()
        persist()
    }
}
