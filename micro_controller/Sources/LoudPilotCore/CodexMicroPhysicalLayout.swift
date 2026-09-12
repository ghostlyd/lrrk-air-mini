import Foundation

/// Physical positions from the Codex Micro reference layout.
///
/// These names describe location only. LoudPilot must not infer a HID
/// signature, joystick axis, or flight function from a position; the live
/// report capture remains the source of truth.
public enum CodexMicroPhysicalControl: String, CaseIterable, Codable, Hashable, Identifiable, Sendable {
    case knob
    case topCenterLeft
    case topCenterRight
    case topRightPlanarJoystick
    case middleLeft
    case middleCenterLeft
    case middleCenterRight
    case middleRight
    case lowerLeft
    case lowerCenterLeft
    case lowerCenterRight
    case lowerRight
    case bottomLeftTouch
    case bottomWide
    case bottomRight

    public var id: String { rawValue }

    public var label: String {
        switch self {
        case .knob: return "Top-left knob"
        case .topCenterLeft: return "Top center-left"
        case .topCenterRight: return "Top center-right"
        case .topRightPlanarJoystick: return "Top-right planar joystick"
        case .middleLeft: return "Middle left"
        case .middleCenterLeft: return "Middle center-left"
        case .middleCenterRight: return "Middle center-right"
        case .middleRight: return "Middle right"
        case .lowerLeft: return "Lower left"
        case .lowerCenterLeft: return "Lower center-left"
        case .lowerCenterRight: return "Lower center-right"
        case .lowerRight: return "Lower right"
        case .bottomLeftTouch: return "Bottom-left touch sensor"
        case .bottomWide: return "Bottom wide"
        case .bottomRight: return "Bottom right"
        }
    }

    public var shortLabel: String {
        switch self {
        case .knob: return "K"
        case .topCenterLeft: return "T1"
        case .topCenterRight: return "T2"
        case .topRightPlanarJoystick: return "JS"
        case .middleLeft: return "M1"
        case .middleCenterLeft: return "M2"
        case .middleCenterRight: return "M3"
        case .middleRight: return "M4"
        case .lowerLeft: return "L1"
        case .lowerCenterLeft: return "L2"
        case .lowerCenterRight: return "L3"
        case .lowerRight: return "L4"
        case .bottomLeftTouch: return "TS"
        case .bottomWide: return "BW"
        case .bottomRight: return "BR"
        }
    }

    public var isKnob: Bool { self == .knob }

    public var shape: CodexMicroPhysicalShape {
        switch self {
        case .knob: return .knob
        case .topRightPlanarJoystick: return .directional
        case .bottomLeftTouch: return .small
        case .bottomWide: return .wide
        default: return .key
        }
    }

    /// Center coordinates measured against the supplied 365x365 reference.
    /// The values are normalized so the native UI can scale without changing
    /// the physical relationships.
    public var normalizedCenter: (x: Double, y: Double) {
        switch self {
        case .knob: return (0.198, 0.198)
        case .topCenterLeft: return (0.410, 0.198)
        case .topCenterRight: return (0.619, 0.198)
        case .topRightPlanarJoystick: return (0.833, 0.198)
        case .middleLeft: return (0.198, 0.414)
        case .middleCenterLeft: return (0.410, 0.414)
        case .middleCenterRight: return (0.619, 0.414)
        case .middleRight: return (0.833, 0.414)
        case .lowerLeft: return (0.198, 0.626)
        case .lowerCenterLeft: return (0.410, 0.626)
        case .lowerCenterRight: return (0.619, 0.626)
        case .lowerRight: return (0.833, 0.626)
        case .bottomLeftTouch: return (0.198, 0.833)
        case .bottomWide: return (0.507, 0.833)
        case .bottomRight: return (0.833, 0.833)
        }
    }

    public var normalizedSize: (width: Double, height: Double) {
        switch shape {
        case .knob: return (0.194, 0.194)
        case .key: return (0.166, 0.166)
        case .directional: return (0.143, 0.143)
        case .small: return (0.094, 0.094)
        case .wide: return (0.382, 0.166)
        }
    }
}

public enum CodexMicroPhysicalShape: String, Codable, Sendable {
    case knob
    case key
    case directional
    case small
    case wide
}

/// UI-stage assignments. These are intentionally separate from HID report
/// bindings and cannot enable a flight transport by themselves.
public enum CodexMicroAssignment: String, CaseIterable, Codable, Hashable, Identifiable, Sendable {
    case unassigned
    case rollLeft
    case rollRight
    case pitchForward
    case pitchBack
    case yawLeft
    case yawRight
    case verticalUp
    case verticalDown
    case emergencyStop
    case rotate360

    public var id: String { rawValue }

    public var label: String {
        switch self {
        case .unassigned: return "Unassigned"
        case .rollLeft: return "Roll left"
        case .rollRight: return "Roll right"
        case .pitchForward: return "Pitch forward"
        case .pitchBack: return "Pitch back"
        case .yawLeft: return "Yaw left"
        case .yawRight: return "Yaw right"
        case .verticalUp: return "Vertical up"
        case .verticalDown: return "Vertical down"
        case .emergencyStop: return "Emergency stop"
        case .rotate360: return "360° rotation"
        }
    }

    public var shortLabel: String {
        switch self {
        case .unassigned: return "—"
        case .rollLeft: return "RL"
        case .rollRight: return "RR"
        case .pitchForward: return "PF"
        case .pitchBack: return "PB"
        case .yawLeft: return "YL"
        case .yawRight: return "YR"
        case .verticalUp: return "UP"
        case .verticalDown: return "DN"
        case .emergencyStop: return "STOP"
        case .rotate360: return "360°"
        }
    }

    public var isRotation: Bool { self == .rotate360 }

    public func isAllowed(on control: CodexMicroPhysicalControl) -> Bool {
        if self == .unassigned { return true }
        if self == .rotate360 { return control.isKnob }
        if control.isKnob {
            return self == .verticalUp || self == .verticalDown
        }
        return true
    }
}
