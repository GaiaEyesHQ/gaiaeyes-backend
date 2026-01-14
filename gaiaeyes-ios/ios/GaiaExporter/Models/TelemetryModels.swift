import Foundation

public struct Sample: Codable, Equatable {
    public let user_id: String
    public let device_os: String
    public let source: String
    public let type: String
    public let start_time: String
    public let end_time: String
    public let value: Double?
    public let unit: String?
    public let value_text: String?

    public init(user_id: String, device_os: String, source: String, type: String,
                start_time: String, end_time: String, value: Double?, unit: String?, value_text: String?) {
        self.user_id = user_id
        self.device_os = device_os
        self.source = source
        self.type = type
        self.start_time = start_time
        self.end_time = end_time
        self.value = value
        self.unit = unit
        self.value_text = value_text
    }
}
public typealias SampleOut = Sample

public struct SamplesBatchPayload: Codable, Equatable {
    public let samples: [Sample]
}
