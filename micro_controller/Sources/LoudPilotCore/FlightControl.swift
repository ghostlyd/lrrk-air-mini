import Foundation

public struct FlightCommand: Equatable, Codable, Sendable {
    /// Roll and pitch are degrees in LiteWing's legacy RPYT commander packet.
    public let rollDegrees: Float
    public let pitchDegrees: Float
    /// Yaw is interpreted by the firmware according to its configured
    /// stabilization mode; the default firmware uses a rate value.
    public let yawDegreesPerSecond: Float
    public let thrust: UInt16

    public init(
        rollDegrees: Double,
        pitchDegrees: Double,
        yawDegreesPerSecond: Double,
        thrust: UInt16
    ) {
        self.rollDegrees = Float(rollDegrees)
        self.pitchDegrees = Float(pitchDegrees)
        self.yawDegreesPerSecond = Float(yawDegreesPerSecond)
        self.thrust = thrust
    }

    public init(
        rollDegrees: Float,
        pitchDegrees: Float,
        yawDegreesPerSecond: Float,
        thrust: UInt16
    ) {
        self.rollDegrees = rollDegrees
        self.pitchDegrees = pitchDegrees
        self.yawDegreesPerSecond = yawDegreesPerSecond
        self.thrust = thrust
    }
}

/// Converts LoudPilot's normalized intent values into LiteWing's legacy
/// commander units. The limits match the ranges used by the firmware's
/// legacy Wi-Fi adapter and are configurable for later bench validation.
public struct FlightCommandMapper: Equatable, Sendable {
    public let maxAttitudeDegrees: Double
    public let maxYawDegreesPerSecond: Double
    public let maxThrust: UInt16

    public init(
        maxAttitudeDegrees: Double = 15,
        maxYawDegreesPerSecond: Double = 15,
        maxThrust: UInt16 = 59000
    ) {
        self.maxAttitudeDegrees = maxAttitudeDegrees
        self.maxYawDegreesPerSecond = maxYawDegreesPerSecond
        self.maxThrust = maxThrust
    }

    public func command(for values: IntendedControlValues) -> FlightCommand {
        FlightCommand(
            rollDegrees: bounded(values.roll, to: -1...1) * maxAttitudeDegrees,
            pitchDegrees: bounded(values.pitch, to: -1...1) * maxAttitudeDegrees,
            yawDegreesPerSecond: bounded(values.yaw, to: -1...1) * maxYawDegreesPerSecond,
            thrust: UInt16((bounded(values.thrust, to: 0...1) * Double(maxThrust)).rounded())
        )
    }

    private func bounded(_ value: Double, to range: ClosedRange<Double>) -> Double {
        guard value.isFinite else { return 0 }
        return Swift.min(Swift.max(value, range.lowerBound), range.upperBound)
    }
}

/// Encoder for the LiteWing firmware's CRTP legacy RPYT commander packet.
///
/// This is intentionally separate from telemetry discovery. It makes the
/// application control-capable without allowing telemetry code to accidentally
/// manufacture a flight packet. A caller still has to explicitly choose to
/// invoke this encoder and send the resulting datagram.
public enum FlightCommandWire {
    public static let setpointHeader: UInt8 = 0x30
    private static let bodyLength = 15

    public static func encodeRPYT(_ command: FlightCommand) throws -> [UInt8] {
        guard command.rollDegrees.isFinite,
              command.pitchDegrees.isFinite,
              command.yawDegreesPerSecond.isFinite else {
            throw TelemetryWireError.malformedFlightCommand
        }

        var body = [setpointHeader]
        appendFloat(command.rollDegrees, to: &body)
        appendFloat(command.pitchDegrees, to: &body)
        appendFloat(command.yawDegreesPerSecond, to: &body)
        body.append(UInt8(command.thrust & 0xFF))
        body.append(UInt8(command.thrust >> 8))
        guard body.count == bodyLength else {
            throw TelemetryWireError.malformedFlightCommand
        }
        return body + [body.reduce(UInt8(0), &+)]
    }

    public static func decodeRPYT(_ packet: [UInt8]) throws -> FlightCommand {
        guard packet.count == bodyLength + 1,
              packet.first == setpointHeader else {
            throw TelemetryWireError.malformedFlightCommand
        }
        let body = Array(packet.dropLast())
        guard body.reduce(UInt8(0), &+) == packet.last else {
            throw TelemetryWireError.checksumMismatch
        }
        return FlightCommand(
            rollDegrees: readFloat(body, offset: 1),
            pitchDegrees: readFloat(body, offset: 5),
            yawDegreesPerSecond: readFloat(body, offset: 9),
            thrust: UInt16(body[13]) | UInt16(body[14]) << 8
        )
    }

    private static func appendFloat(_ value: Float, to bytes: inout [UInt8]) {
        let raw = value.bitPattern
        bytes.append(UInt8(raw & 0xFF))
        bytes.append(UInt8((raw >> 8) & 0xFF))
        bytes.append(UInt8((raw >> 16) & 0xFF))
        bytes.append(UInt8((raw >> 24) & 0xFF))
    }

    private static func readFloat(_ bytes: [UInt8], offset: Int) -> Float {
        let raw = UInt32(bytes[offset]) |
            UInt32(bytes[offset + 1]) << 8 |
            UInt32(bytes[offset + 2]) << 16 |
            UInt32(bytes[offset + 3]) << 24
        return Float(bitPattern: raw)
    }
}
