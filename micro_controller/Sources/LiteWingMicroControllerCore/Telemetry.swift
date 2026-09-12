import Foundation

public enum TelemetryWireError: Error, Equatable, CustomStringConvertible {
    case flightPortDisabled
    case malformedPacket
    case checksumMismatch
    case malformedTOCItem
    case malformedLogData
    case unsupportedLogType(UInt8)

    public var description: String {
        switch self {
        case .flightPortDisabled: return "flight-control CRTP ports are disabled"
        case .malformedPacket: return "malformed CRTP/UDP packet"
        case .checksumMismatch: return "CRTP/UDP checksum mismatch"
        case .malformedTOCItem: return "malformed log TOC item"
        case .malformedLogData: return "malformed log data"
        case .unsupportedLogType(let value): return "unsupported log type \(value)"
        }
    }
}

public struct DecodedTelemetryPacket: Equatable, Sendable {
    public let header: UInt8
    public let payload: [UInt8]

    public init(header: UInt8, payload: [UInt8]) {
        self.header = header
        self.payload = payload
    }
}

/// The manufacturer firmware wraps each CRTP packet in a one-byte additive
/// checksum. This codec exposes only the log port (0x5); setpoint and other
/// flight-control ports are rejected before a datagram can be produced.
public enum ReadOnlyTelemetryWire {
    private static let logPort: UInt8 = 0x50
    private static let maxCRTPData = 30

    public static let flightCommandTransmissionEnabled = false

    public static func encode(header: UInt8, payload: [UInt8]) throws -> [UInt8] {
        guard header & 0xF0 == logPort else {
            throw TelemetryWireError.flightPortDisabled
        }
        guard payload.count <= maxCRTPData else {
            throw TelemetryWireError.malformedPacket
        }
        let body = [header] + payload
        let checksum = body.reduce(UInt8(0), &+)
        return body + [checksum]
    }

    public static func decode(_ packet: [UInt8]) throws -> DecodedTelemetryPacket {
        guard packet.count >= 2 else { throw TelemetryWireError.malformedPacket }
        let body = packet.dropLast()
        let checksum = body.reduce(UInt8(0), &+)
        guard checksum == packet.last else { throw TelemetryWireError.checksumMismatch }
        guard body.count <= maxCRTPData + 1 else { throw TelemetryWireError.malformedPacket }
        let header = body[body.startIndex]
        guard header & 0xF0 == logPort else { throw TelemetryWireError.flightPortDisabled }
        return DecodedTelemetryPacket(header: header, payload: Array(body.dropFirst()))
    }

    public static func logTOCInfoRequest() throws -> [UInt8] {
        try encode(header: logPort, payload: [3])
    }

    public static func logTOCItemRequest(id: UInt16) throws -> [UInt8] {
        try encode(header: logPort, payload: [2, UInt8(id & 0xFF), UInt8(id >> 8)])
    }

    public static func logCreateBlockRequest(
        blockID: UInt8,
        variables: [LogVariable]
    ) throws -> [UInt8] {
        var payload: [UInt8] = [6, blockID]
        for variable in variables {
            payload.append(variable.type.rawValue)
            payload.append(UInt8(variable.id & 0xFF))
            payload.append(UInt8(variable.id >> 8))
        }
        return try encode(header: logPort | 1, payload: payload)
    }

    public static func logStartBlockRequest(blockID: UInt8, periodMilliseconds: UInt16) throws -> [UInt8] {
        let ticks = max(1, min(255, Int((Double(periodMilliseconds) / 10.0).rounded())))
        return try encode(header: logPort | 1, payload: [3, blockID, UInt8(ticks)])
    }

    public static func decodeTOCItem(_ payload: [UInt8]) throws -> LogVariable {
        guard payload.count >= 6, payload[0] == 2 else {
            throw TelemetryWireError.malformedTOCItem
        }
        let id = UInt16(payload[1]) | (UInt16(payload[2]) << 8)
        guard let type = LogValueType(rawValue: payload[3]) else {
            throw TelemetryWireError.unsupportedLogType(payload[3])
        }
        let strings = Array(payload.dropFirst(4))
        guard let groupEnd = strings.firstIndex(of: 0) else {
            throw TelemetryWireError.malformedTOCItem
        }
        let nameStart = groupEnd + 1
        guard nameStart < strings.count,
              let nameEnd = strings[nameStart...].firstIndex(of: 0) else {
            throw TelemetryWireError.malformedTOCItem
        }
        let group = String(decoding: strings[..<groupEnd], as: UTF8.self)
        let name = String(decoding: strings[nameStart..<nameEnd], as: UTF8.self)
        guard !group.isEmpty, !name.isEmpty else {
            throw TelemetryWireError.malformedTOCItem
        }
        return LogVariable(id: id, type: type, group: group, name: name)
    }
}

public enum LogValueType: UInt8, Equatable, Sendable {
    case uint8 = 1
    case uint16 = 2
    case uint32 = 3
    case int8 = 4
    case int16 = 5
    case int32 = 6
    case float32 = 7
    case float16 = 8

    public var byteCount: Int {
        switch self {
        case .uint8, .int8: return 1
        case .uint16, .int16, .float16: return 2
        case .uint32, .int32, .float32: return 4
        }
    }
}

public struct LogVariable: Equatable, Sendable {
    public let id: UInt16
    public let type: LogValueType
    public let group: String
    public let name: String

    public init(id: UInt16, type: LogValueType, group: String, name: String) {
        self.id = id
        self.type = type
        self.group = group
        self.name = name
    }

    public var path: String { "\(group).\(name)" }
}

public struct LogBlockSchema: Equatable, Sendable {
    public let blockID: UInt8
    public let variables: [LogVariable]

    public init(blockID: UInt8, variables: [LogVariable]) {
        self.blockID = blockID
        self.variables = variables
    }
}

public struct Vector3: Equatable, Sendable {
    public let x: Double
    public let y: Double
    public let z: Double

    public init(x: Double, y: Double, z: Double) {
        self.x = x
        self.y = y
        self.z = z
    }
}

public struct DroneTelemetryState: Equatable, Sendable {
    public private(set) var batteryVoltage: Double?
    public private(set) var gyro: Vector3?
    public private(set) var accelerometer: Vector3?
    /// Always nil in this first stage unless a separately verified source is added.
    public private(set) var positioning: String?
    public private(set) var lastReceivedAt: TimeInterval?

    private var gyroParts: [String: Double] = [:]
    private var accelerometerParts: [String: Double] = [:]

    public init() {}

    public mutating func applyLogData(
        _ data: [UInt8],
        schema: LogBlockSchema,
        receivedAt: TimeInterval
    ) throws {
        guard data.count >= 4, data[0] == schema.blockID else {
            throw TelemetryWireError.malformedLogData
        }
        var offset = 4
        var newValues: [(LogVariable, Double)] = []
        for variable in schema.variables {
            let end = offset + variable.type.byteCount
            guard end <= data.count else { throw TelemetryWireError.malformedLogData }
            let value = try decodeValue(data[offset..<end], type: variable.type)
            newValues.append((variable, value))
            offset = end
        }
        guard offset == data.count else { throw TelemetryWireError.malformedLogData }

        for (variable, value) in newValues {
            switch variable.path {
            case "pm.vbat":
                batteryVoltage = value.isFinite ? value : nil
            case "gyro.x", "gyro.y", "gyro.z":
                gyroParts[variable.name] = value
            case "acc.x", "acc.y", "acc.z":
                accelerometerParts[variable.name] = value
            default:
                break
            }
        }
        if let x = gyroParts["x"], let y = gyroParts["y"], let z = gyroParts["z"] {
            gyro = Vector3(x: x, y: y, z: z)
        }
        if let x = accelerometerParts["x"], let y = accelerometerParts["y"], let z = accelerometerParts["z"] {
            accelerometer = Vector3(x: x, y: y, z: z)
        }
        lastReceivedAt = receivedAt
    }

    public func telemetryAge(now: TimeInterval) -> TimeInterval? {
        guard let lastReceivedAt else { return nil }
        return max(0, now - lastReceivedAt)
    }

    private func decodeValue(_ bytes: ArraySlice<UInt8>, type: LogValueType) throws -> Double {
        let b = Array(bytes)
        switch type {
        case .uint8: return Double(b[0])
        case .int8: return Double(Int8(bitPattern: b[0]))
        case .uint16: return Double(UInt16(b[0]) | UInt16(b[1]) << 8)
        case .int16: return Double(Int16(bitPattern: UInt16(b[0]) | UInt16(b[1]) << 8))
        case .uint32:
            return Double(UInt32(b[0]) | UInt32(b[1]) << 8 | UInt32(b[2]) << 16 | UInt32(b[3]) << 24)
        case .int32:
            let raw = UInt32(b[0]) | UInt32(b[1]) << 8 | UInt32(b[2]) << 16 | UInt32(b[3]) << 24
            return Double(Int32(bitPattern: raw))
        case .float32:
            let raw = UInt32(b[0]) | UInt32(b[1]) << 8 | UInt32(b[2]) << 16 | UInt32(b[3]) << 24
            return Double(Float(bitPattern: raw))
        case .float16:
            throw TelemetryWireError.unsupportedLogType(type.rawValue)
        }
    }
}
