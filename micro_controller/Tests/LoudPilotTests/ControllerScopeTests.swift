import LoudPilotCore

enum ControllerScopeTests {
    static func testOnlyCodexMicroIsInControllerScope() throws {
        let codex = HIDDeviceSummary(
            id: "usb-codex",
            product: "Codex Micro",
            manufacturer: "OpenAI",
            transport: "USB",
            vendorID: 0x303A,
            productID: 0x8360
        )
        let workLouder = HIDDeviceSummary(
            id: "bt-work-louder",
            product: "Work Louder Micro",
            manufacturer: "Work Louder",
            transport: "Bluetooth",
            vendorID: 0,
            productID: 0
        )
        let keyboard = HIDDeviceSummary(
            id: "magic-keyboard",
            product: "Magic Keyboard",
            manufacturer: "Apple",
            transport: "Bluetooth",
            vendorID: 0x4C,
            productID: 0x322
        )

        try expect(codex.isControllerCandidate, "Codex Micro should be the controller candidate")
        try expect(workLouder.isControllerCandidate, "Work Louder Micro should be the controller candidate")
        try expect(!keyboard.isControllerCandidate, "Apple Magic Keyboard must be outside the Codex Micro controller scope")
    }

    static func testBluetoothDiscoveryRetainsMicroCandidatesAndMarksKeyboardOutOfScope() throws {
        let peripherals = [
            BluetoothPeripheralSummary(id: "keyboard", name: "Mark’s Magic Keyboard", rssi: -42),
            BluetoothPeripheralSummary(id: "micro", name: "Codex Micro #2", rssi: -58),
            BluetoothPeripheralSummary(id: "mouse", name: "Magic Mouse", rssi: -61)
        ]

        let candidates = BluetoothDiscoveryPolicy.controllerCandidates(from: peripherals)
        try expect(candidates.map(\.id) == ["micro"], "Bluetooth discovery must retain only Codex Micro names")
        try expect(!peripherals[0].isControllerCandidate, "Magic Keyboard must be visible but out of controller scope")
    }

    static func testOutOfScopeHIDCannotAcquirePilotProfile() throws {
        let keyboard = HIDDeviceSummary(
            id: "keyboard",
            product: "Magic Keyboard",
            manufacturer: "Apple",
            transport: "Bluetooth",
            vendorID: 0x4C,
            productID: 0x322
        )
        let codex = HIDDeviceSummary(
            id: "micro",
            product: "Codex Micro",
            manufacturer: "OpenAI",
            transport: "USB",
            vendorID: 0x303A,
            productID: 0x8360
        )

        try expect(ControllerInputPolicy.profile(for: keyboard) == BuiltInControlProfiles.unmapped, "out-of-scope HID must remain unmapped")
        try expect(ControllerInputPolicy.capturePlan(for: keyboard) == nil, "out-of-scope HID must not receive a capture plan")
        try expect(ControllerInputPolicy.profile(for: codex) == BuiltInControlProfiles.codexMicro, "Codex Micro must receive the controller profile")
    }

    static func testCommanderSetpointUsesLiteWingCRTPSetpointPort() throws {
        let command = FlightCommand(
            rollDegrees: 1.5,
            pitchDegrees: -2.0,
            yawDegreesPerSecond: 3.0,
            thrust: 12000
        )
        let packet = try FlightCommandWire.encodeRPYT(command)
        try expect(packet.first == 0x30, "commander RPYT must use CRTP port 3 channel 0")
        try expect(packet.count == 16, "commander packet must contain header, 14-byte payload, and checksum")
        try expect(packet.dropLast().reduce(UInt8(0), &+) == packet.last, "commander packet must use the LiteWing UDP checksum")

        let decoded = try FlightCommandWire.decodeRPYT(packet)
        try expect(decoded == command, "commander packet should round-trip without changing setpoint values")
    }

    static func testNormalizedIntentMapsToLiteWingCommanderRange() throws {
        let values = IntendedControlValues(roll: 1, pitch: -0.5, yaw: 0.25, thrust: 0.5)
        let command = FlightCommandMapper().command(for: values)

        try expect(command.rollDegrees == 15, "full positive roll intent should map to the LiteWing roll limit")
        try expect(command.pitchDegrees == -7.5, "half negative pitch intent should map proportionally")
        try expect(command.yawDegreesPerSecond == 3.75, "yaw intent should map to the configured rate limit")
        try expect(command.thrust == 29500, "normalized thrust should map to the legacy LiteWing range")
    }
}
