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
        guard !descriptor.isRelative else { return nil }
        return actions[HIDUsage(page: descriptor.usagePage, usage: descriptor.usage)]
    }
}

public enum BuiltInControlProfiles {
    /// Conventional keyboard pilot layout. This produces intended values only;
    /// the desktop app still has no flight-command transport.
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
