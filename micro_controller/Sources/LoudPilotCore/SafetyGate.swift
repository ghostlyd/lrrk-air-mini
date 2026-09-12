import Foundation

/// Freshness of the read-only sensor stream used by the future control plane.
/// Only a decoded sensor packet can move the state to `fresh`; Wi-Fi path
/// availability or a control ACK is not sufficient.
public enum TelemetryFreshness: String, Equatable, Sendable {
    case unavailable
    case fresh
    case stale

    public var inhibitsOutput: Bool {
        self != .fresh
    }

    public var label: String {
        switch self {
        case .unavailable: return "Unavailable"
        case .fresh: return "Fresh"
        case .stale: return "Stale"
        }
    }
}

/// Fail-closed boundary for any future flight-command sender.
///
/// LoudPilot's current application never connects the output transport, so
/// `canTransmit` remains false even after read-only telemetry becomes fresh.
/// Keeping the complete gate in the core makes link loss, focus loss,
/// disconnects, incomplete mapping, and the emergency stop explicit rather
/// than relying on a UI convention.
public struct FlightOutputGate: Equatable, Sendable {
    public var inputConnected: Bool
    public var appFocused: Bool
    public var telemetryFreshness: TelemetryFreshness
    public var mappingStaged: Bool
    public var emergencyStopLatched: Bool
    public var outputTransportConnected: Bool

    public init(
        inputConnected: Bool = false,
        appFocused: Bool = false,
        telemetryFreshness: TelemetryFreshness = .unavailable,
        mappingStaged: Bool = false,
        emergencyStopLatched: Bool = false,
        outputTransportConnected: Bool = false
    ) {
        self.inputConnected = inputConnected
        self.appFocused = appFocused
        self.telemetryFreshness = telemetryFreshness
        self.mappingStaged = mappingStaged
        self.emergencyStopLatched = emergencyStopLatched
        self.outputTransportConnected = outputTransportConnected
    }

    public var failsafeActive: Bool {
        !blockingReasons.isEmpty
    }

    public var canTransmit: Bool {
        blockingReasons.isEmpty
    }

    public var blockingReasons: [String] {
        var reasons: [String] = []
        if !inputConnected { reasons.append("controller disconnected") }
        if !appFocused { reasons.append("application focus lost") }
        if telemetryFreshness == .unavailable {
            reasons.append("telemetry unavailable")
        } else if telemetryFreshness == .stale {
            reasons.append("telemetry stale")
        }
        if !mappingStaged { reasons.append("mapping not staged") }
        if emergencyStopLatched { reasons.append("emergency stop latched") }
        if !outputTransportConnected { reasons.append("flight output transport disconnected") }
        return reasons
    }
}
