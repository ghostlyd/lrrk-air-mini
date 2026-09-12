import Foundation

public struct HIDUsage: Hashable, Equatable, Sendable {
    public let page: UInt32
    public let usage: UInt32

    public init(page: UInt32, usage: UInt32) {
        self.page = page
        self.usage = usage
    }
}

public enum HIDProfileAction: Equatable, Sendable {
    case control(IntendedControl, Double)
    case relativeControl(IntendedControl, Double)
    case stop
}

public struct HIDControlProfile: Equatable, Sendable {
    public let name: String
    private let actions: [HIDUsage: HIDProfileAction]

    public init(name: String, actions: [HIDUsage: HIDProfileAction]) {
        self.name = name
        self.actions = actions
    }

    public func action(for descriptor: HIDElementDescriptor) -> HIDProfileAction? {
        return actions[HIDUsage(page: descriptor.usagePage, usage: descriptor.usage)]
    }
}

public struct CodexMicroMapping: Equatable, Sendable {
    public let profile: HIDControlProfile
    public let summary: String

    public init(profile: HIDControlProfile, summary: String) {
        self.profile = profile
        self.summary = summary
    }
}

public enum CodexMicroMappingPolicy {
    /// Converts only a complete, accepted capture into a staged profile.
    ///
    /// Four learned button reports provide digital roll/pitch directions, the
    /// relative knob report provides normalized yaw deltas, and the fifth
    /// learned button report is a latched stop. Thrust remains unbound until
    /// a later, separately validated control stage.
    public static func stagedMapping(
        from capture: GuidedCaptureState,
        interactionEvidence: HIDInteractionEvidence
    ) -> CodexMicroMapping? {
        guard interactionEvidence.maximumConcurrentInputs >= 2,
              interactionEvidence.simultaneousInputSessions >= 1 else {
            return nil
        }
        guard capture.isComplete else { return nil }
        let buttonIDs = (1...5).map { "button-\($0)" }
        let buttonSignatures = buttonIDs.compactMap { capture.acceptedSignatureByStep[$0] }
        guard buttonSignatures.count == 5,
              Set(buttonSignatures).count == 5,
              let dialClockwise = capture.acceptedSignatureByStep["dial-clockwise"],
              let dialCounterclockwise = capture.acceptedSignatureByStep["dial-counterclockwise"],
              dialClockwise == dialCounterclockwise,
              let clockwiseSign = capture.dialSignByStep["dial-clockwise"],
              let counterclockwiseSign = capture.dialSignByStep["dial-counterclockwise"],
              clockwiseSign != 0,
              counterclockwiseSign == -clockwiseSign else {
            return nil
        }

        let buttonUsages = buttonSignatures.map { HIDUsage(page: $0.usagePage, usage: $0.usage) }
        guard Set(buttonUsages).count == 5 else { return nil }

        let actions: [HIDUsage: HIDProfileAction] = [
            buttonUsages[0]: .control(.roll, -1),
            buttonUsages[1]: .control(.roll, 1),
            buttonUsages[2]: .control(.pitch, 1),
            buttonUsages[3]: .control(.pitch, -1),
            buttonUsages[4]: .stop,
            HIDUsage(page: dialClockwise.usagePage, usage: dialClockwise.usage): .relativeControl(.yaw, Double(clockwiseSign))
        ]

        return CodexMicroMapping(
            profile: HIDControlProfile(name: "Codex Micro · learned staged mapping", actions: actions),
            summary: "Learned buttons 1–4 roll/pitch · learned button 5 emergency stop · knob yaw · simultaneous input verified · thrust unbound"
        )
    }
}

public enum BuiltInControlProfiles {
    /// Legacy keyboard layout retained for compatibility with older fixtures.
    /// `ControllerInputPolicy` never exposes it to the LoudPilot app.
    public static let magicKeyboard = HIDControlProfile(
        name: "Apple Magic Keyboard · WASD/QE/RF",
        actions: [
            HIDUsage(page: 0x07, usage: 0x1A): .control(.pitch, 1),   // W
            HIDUsage(page: 0x07, usage: 0x16): .control(.pitch, -1),  // S
            HIDUsage(page: 0x07, usage: 0x04): .control(.roll, -1),   // A
            HIDUsage(page: 0x07, usage: 0x07): .control(.roll, 1),    // D
            HIDUsage(page: 0x07, usage: 0x14): .control(.yaw, -1),    // Q
            HIDUsage(page: 0x07, usage: 0x08): .control(.yaw, 1),     // E
            HIDUsage(page: 0x07, usage: 0x15): .control(.thrust, 1),  // R
            HIDUsage(page: 0x07, usage: 0x09): .control(.thrust, -1), // F
            HIDUsage(page: 0x07, usage: 0x52): .control(.pitch, 1),   // Up
            HIDUsage(page: 0x07, usage: 0x51): .control(.pitch, -1),  // Down
            HIDUsage(page: 0x07, usage: 0x50): .control(.roll, -1),   // Left
            HIDUsage(page: 0x07, usage: 0x4F): .control(.roll, 1),    // Right
            HIDUsage(page: 0x07, usage: 0x29): .stop,                 // Escape
        ]
    )

    /// The Micro report layout is intentionally not guessed. It becomes a
    /// mapped profile only after its live HID reports are observed.
    public static let codexMicro = HIDControlProfile(
        name: "Codex Micro · report review required",
        actions: [:]
    )

    public static let unmapped = HIDControlProfile(name: "Unmapped HID device", actions: [:])
}

/// Single source of truth for the app's physical controller scope.
public enum ControllerInputPolicy {
    public static func profile(for device: HIDDeviceSummary) -> HIDControlProfile {
        device.isControllerCandidate
            ? BuiltInControlProfiles.codexMicro
            : BuiltInControlProfiles.unmapped
    }

    public static func capturePlan(for device: HIDDeviceSummary) -> GuidedCapturePlan? {
        device.isControllerCandidate ? .codexMicro : nil
    }
}
