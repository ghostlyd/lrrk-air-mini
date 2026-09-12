import Foundation

public enum MicroInputKind: String, Equatable, Codable, Sendable {
    case key
    case button
    case dial
    case axis
    case unknown
}

public enum MicroInputPhase: String, Equatable, Codable, Sendable {
    case pressed
    case held
    case released
    case dial
    case value
}

public enum HIDInputPolicy {
    /// Vendor-specific streams can carry device telemetry or diagnostics.
    /// They are never surfaced as physical controls without a decoded schema.
    public static func shouldSurfaceAsPhysicalEvent(_ event: MicroInputEvent) -> Bool {
        event.kind != .unknown
    }
}

public enum IntendedControl: String, CaseIterable, Equatable, Codable, Sendable {
    case roll
    case pitch
    case yaw
    case thrust
}

public struct IntendedControlValues: Equatable, Codable, Sendable {
    public var roll: Double
    public var pitch: Double
    public var yaw: Double
    public var thrust: Double

    public init(
        roll: Double = 0,
        pitch: Double = 0,
        yaw: Double = 0,
        thrust: Double = 0
    ) {
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.thrust = thrust
    }

    public var isZero: Bool {
        abs(roll) < 0.000001 &&
            abs(pitch) < 0.000001 &&
            abs(yaw) < 0.000001 &&
            abs(thrust) < 0.000001
    }
}

public struct InputBinding: Equatable, Codable, Sendable {
    public let control: IntendedControl
    public let scale: Double

    public init(control: IntendedControl, scale: Double) {
        self.control = control
        self.scale = scale
    }
}

public struct MicroInputEvent: Equatable, Codable, Sendable {
    public let identifier: String
    public let kind: MicroInputKind
    public let value: Double
    public let phase: MicroInputPhase
    public let timestamp: TimeInterval
    public let controlMapping: IntendedControl?
    public let controlScale: Double

    public init(
        identifier: String,
        kind: MicroInputKind,
        value: Double,
        phase: MicroInputPhase,
        timestamp: TimeInterval,
        controlMapping: IntendedControl? = nil,
        controlScale: Double = 1
    ) {
        self.identifier = identifier
        self.kind = kind
        self.value = value
        self.phase = phase
        self.timestamp = timestamp
        self.controlMapping = controlMapping
        self.controlScale = controlScale
    }
}

public struct HIDElementDescriptor: Equatable, Sendable {
    public let identifier: String
    public let usagePage: UInt32
    public let usage: UInt32
    public let isRelative: Bool

    public init(identifier: String, usagePage: UInt32, usage: UInt32, isRelative: Bool) {
        self.identifier = identifier
        self.usagePage = usagePage
        self.usage = usage
        self.isRelative = isRelative
    }
}

/// Converts observed HID element values to lifecycle events. It reports axes
/// as raw values and intentionally never maps them to flight controls.
public struct HIDInputInterpreter: Sendable {
    public private(set) var activeElementIDs: Set<String> = []

    public init() {}

    public mutating func ingest(
        descriptor: HIDElementDescriptor,
        value: Double,
        timestamp: TimeInterval
    ) -> MicroInputEvent {
        let kind = classify(descriptor)
        if kind == .dial {
            return MicroInputEvent(
                identifier: descriptor.identifier,
                kind: .dial,
                value: value,
                phase: .dial,
                timestamp: timestamp
            )
        }
        if kind == .axis {
            return MicroInputEvent(
                identifier: descriptor.identifier,
                kind: .axis,
                value: value,
                phase: .value,
                timestamp: timestamp
            )
        }

        let wasActive = activeElementIDs.contains(descriptor.identifier)
        let isActive = abs(value) > 0.000001
        let phase: MicroInputPhase
        if isActive {
            phase = wasActive ? .held : .pressed
            activeElementIDs.insert(descriptor.identifier)
        } else {
            phase = .released
            activeElementIDs.remove(descriptor.identifier)
        }
        return MicroInputEvent(
            identifier: descriptor.identifier,
            kind: kind,
            value: value,
            phase: phase,
            timestamp: timestamp
        )
    }

    private func classify(_ descriptor: HIDElementDescriptor) -> MicroInputKind {
        switch descriptor.usagePage {
        case 0x07:
            return .key
        case 0x09:
            return .button
        case 0x01 where descriptor.usage == 0x38 && descriptor.isRelative:
            return .dial
        case 0x0C where descriptor.isRelative:
            return .dial
        case 0x01 where (0x30...0x35).contains(descriptor.usage):
            return .axis
        default:
            return .unknown
        }
    }
}

/// Pure state boundary for a physical Micro input device.
///
/// This type deliberately produces intended values only. It has no network
/// transport and therefore cannot emit a flight command.
public struct InputSafetyState: Equatable, Sendable {
    public private(set) var connected = false
    public private(set) var focused = true
    public private(set) var stopLatched = false
    public private(set) var activeInputs: Set<String> = []
    public private(set) var intended = IntendedControlValues()
    public private(set) var lastDialDelta: Double = 0

    private let bindings: [String: InputBinding]
    private var activeValues: [String: Double] = [:]
    private var activeBindings: [String: InputBinding] = [:]

    public init(bindings: [String: InputBinding]) {
        self.bindings = bindings
    }

    public var controlInputEnabled: Bool {
        connected && focused && !stopLatched
    }

    public mutating func setConnected(_ value: Bool) {
        connected = value
        if !value {
            clearInputs()
        }
    }

    public mutating func setFocused(_ value: Bool) {
        focused = value
        if !value {
            clearInputs()
        }
    }

    public mutating func stop() {
        stopLatched = true
        clearInputs()
    }

    public mutating func clearStop() {
        stopLatched = false
        clearInputs()
    }

    public mutating func ingest(_ event: MicroInputEvent) {
        guard controlInputEnabled else { return }

        if event.kind == .dial || event.phase == .dial {
            lastDialDelta = event.value * event.controlScale
            return
        }

        switch event.phase {
        case .pressed, .held, .value:
            if abs(event.value) < 0.000001 {
                activeValues.removeValue(forKey: event.identifier)
                activeInputs.remove(event.identifier)
                activeBindings.removeValue(forKey: event.identifier)
            } else {
                activeValues[event.identifier] = event.value
                if let mapping = event.controlMapping {
                    activeBindings[event.identifier] = InputBinding(control: mapping, scale: event.controlScale)
                } else if let binding = bindings[event.identifier] {
                    activeBindings[event.identifier] = binding
                } else {
                    activeBindings.removeValue(forKey: event.identifier)
                }
                activeInputs.insert(event.identifier)
            }
        case .released:
            activeValues.removeValue(forKey: event.identifier)
            activeInputs.remove(event.identifier)
            activeBindings.removeValue(forKey: event.identifier)
        case .dial:
            break
        }
        recomputeIntended()
    }

    private mutating func clearInputs() {
        activeValues.removeAll(keepingCapacity: true)
        activeBindings.removeAll(keepingCapacity: true)
        activeInputs.removeAll(keepingCapacity: true)
        intended = IntendedControlValues()
        lastDialDelta = 0
    }

    private mutating func recomputeIntended() {
        var values = IntendedControlValues()
        for (identifier, inputValue) in activeValues {
            guard let binding = activeBindings[identifier] ?? bindings[identifier] else { continue }
            let contribution = inputValue * binding.scale
            switch binding.control {
            case .roll:
                values.roll += contribution
            case .pitch:
                values.pitch += contribution
            case .yaw:
                values.yaw += contribution
            case .thrust:
                values.thrust += contribution
            }
        }
        values.roll = values.roll.clamped(to: -1...1)
        values.pitch = values.pitch.clamped(to: -1...1)
        values.yaw = values.yaw.clamped(to: -1...1)
        values.thrust = values.thrust.clamped(to: 0...1)
        intended = values
    }
}

private extension Double {
    func clamped(to range: ClosedRange<Double>) -> Double {
        Swift.min(Swift.max(self, range.lowerBound), range.upperBound)
    }
}
