import LoudPilotCore

enum PhysicalInputActivityTests {
    static func testButtonActivityPersistsUntilRelease() throws {
        let signature = HIDCaptureSignature(usagePage: 0x09, usage: 4, isRelative: false)
        var state = HIDPhysicalActivityState()

        state.ingest(
            signature: signature,
            event: MicroInputEvent(
                identifier: "button",
                kind: .button,
                value: 1,
                phase: .pressed,
                timestamp: 1
            )
        )
        try expect(state.isActive(signature, now: 10), "a held button should remain active beyond the redraw interval")

        state.ingest(
            signature: signature,
            event: MicroInputEvent(
                identifier: "button",
                kind: .button,
                value: 0,
                phase: .released,
                timestamp: 11
            )
        )
        try expect(!state.isActive(signature, now: 11), "button release should clear the physical activity")
    }

    static func testDialActivityIsRecentButNotLatched() throws {
        let signature = HIDCaptureSignature(usagePage: 0x01, usage: 0x38, isRelative: true)
        var state = HIDPhysicalActivityState()

        state.ingest(
            signature: signature,
            event: MicroInputEvent(
                identifier: "dial",
                kind: .dial,
                value: 1,
                phase: .dial,
                timestamp: 20
            )
        )
        try expect(state.hasRecentActivity(of: .dial, now: 20.5), "a dial turn should light the knob briefly")
        try expect(!state.activeSignatures.contains(signature), "a dial turn must not become a held button")
        try expect(!state.hasRecentActivity(of: .dial, now: 22), "dial activity should expire without a new detent")
    }

    static func testJoystickActivityClearsAtNeutral() throws {
        let signature = HIDCaptureSignature(usagePage: 0x01, usage: 0x30, isRelative: false)
        var state = HIDPhysicalActivityState()

        state.ingest(
            signature: signature,
            event: MicroInputEvent(
                identifier: "axis",
                kind: .axis,
                value: 127,
                phase: .value,
                timestamp: 30
            )
        )
        try expect(state.hasRecentActivity(of: .axis, now: 40), "a non-neutral joystick axis should remain highlighted")

        state.ingest(
            signature: signature,
            event: MicroInputEvent(
                identifier: "axis",
                kind: .axis,
                value: 0,
                phase: .value,
                timestamp: 41
            )
        )
        try expect(!state.hasRecentActivity(of: .axis, now: 41), "a neutral joystick report should clear the highlight")
    }
}
