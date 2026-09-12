import LiteWingMicroControllerCore

enum HIDInputTests {
    static func testDeviceCandidateMatchingUsesMetadataNotJoystickAssumptions() throws {
        let micro = HIDDeviceSummary(
            id: "device-1",
            product: "Codex Micro",
            manufacturer: "OpenAI",
            transport: "Bluetooth",
            vendorID: 42,
            productID: 7
        )
        let keyboard = HIDDeviceSummary(
            id: "device-2",
            product: "Magic Keyboard",
            manufacturer: "Apple",
            transport: "Bluetooth",
            vendorID: 76,
            productID: 802
        )

        try expect(micro.isMicroCandidate, "Micro metadata should be surfaced as a candidate")
        try expect(!keyboard.isMicroCandidate, "unrelated Bluetooth HID should not be auto-selected")
    }

    static func testButtonPressHoldReleaseLifecycle() throws {
        var decoder = HIDInputInterpreter()
        let descriptor = HIDElementDescriptor(
            identifier: "element:7:4",
            usagePage: 0x09,
            usage: 4,
            isRelative: false
        )

        let press = decoder.ingest(descriptor: descriptor, value: 1, timestamp: 1)
        let hold = decoder.ingest(descriptor: descriptor, value: 1, timestamp: 2)
        let release = decoder.ingest(descriptor: descriptor, value: 0, timestamp: 3)

        try expect(press.kind == .button && press.phase == .pressed, "first nonzero button value should be press")
        try expect(hold.kind == .button && hold.phase == .held, "repeated nonzero button value should be hold")
        try expect(release.kind == .button && release.phase == .released, "zero button value should be release")
        try expect(decoder.activeElementIDs.isEmpty, "release should clear the decoder active set")
    }

    static func testSimultaneousButtonsMaintainIndependentActiveIDs() throws {
        var decoder = HIDInputInterpreter()
        let first = HIDElementDescriptor(identifier: "element:9:1", usagePage: 0x09, usage: 1, isRelative: false)
        let second = HIDElementDescriptor(identifier: "element:9:2", usagePage: 0x09, usage: 2, isRelative: false)
        _ = decoder.ingest(descriptor: first, value: 1, timestamp: 1)
        _ = decoder.ingest(descriptor: second, value: 1, timestamp: 1)
        _ = decoder.ingest(descriptor: first, value: 0, timestamp: 2)

        try expect(decoder.activeElementIDs == ["element:9:2"], "releasing one button must not clear another")
    }

    static func testRelativeWheelIsReportedAsDialAndNotAxis() throws {
        var decoder = HIDInputInterpreter()
        let dial = HIDElementDescriptor(identifier: "element:1:56", usagePage: 0x01, usage: 0x38, isRelative: true)
        let event = decoder.ingest(descriptor: dial, value: -2, timestamp: 4)

        try expect(event.kind == .dial, "HID wheel usage should be classified as a dial")
        try expect(event.phase == .dial && event.value == -2, "dial event should retain relative delta")
        try expect(decoder.activeElementIDs.isEmpty, "dial events must not become held buttons")
    }

    static func testGenericDesktopAxisIsObservedButNotMappedAsJoystickCommand() throws {
        var decoder = HIDInputInterpreter()
        let axis = HIDElementDescriptor(identifier: "element:1:48", usagePage: 0x01, usage: 0x30, isRelative: false)
        let event = decoder.ingest(descriptor: axis, value: 127, timestamp: 4)

        try expect(event.kind == .axis, "generic desktop axis should be observable")
        try expect(event.phase == .value, "axis values should not be forced into press semantics")
        try expect(event.controlMapping == nil, "axis should not be assumed to be a proportional joystick control")
    }
}
