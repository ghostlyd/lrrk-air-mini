import LiteWingMicroControllerCore

enum ControlMappingTests {
    static func testMagicKeyboardProfileMapsObservedKeyUsagesAndEscapeStops() throws {
        let profile = BuiltInControlProfiles.magicKeyboard
        let pitchForward = HIDElementDescriptor(
            identifier: "keyboard:w",
            usagePage: 0x07,
            usage: 0x1A,
            isRelative: false
        )
        let escape = HIDElementDescriptor(
            identifier: "keyboard:escape",
            usagePage: 0x07,
            usage: 0x29,
            isRelative: false
        )

        try expect(profile.action(for: pitchForward) == .control(.pitch, 1), "W should map to positive pitch intent")
        try expect(profile.action(for: escape) == .stop, "Escape should be a stop action")
    }

    static func testMappedInputReleaseClearsIntendedValue() throws {
        let descriptor = HIDElementDescriptor(
            identifier: "keyboard:w",
            usagePage: 0x07,
            usage: 0x1A,
            isRelative: false
        )
        var state = InputSafetyState(bindings: [:])
        state.setConnected(true)
        state.ingest(MicroInputEvent(
            identifier: descriptor.identifier,
            kind: .key,
            value: 1,
            phase: .pressed,
            timestamp: 1,
            controlMapping: .pitch,
            controlScale: 1
        ))
        try expect(state.intended.pitch == 1, "mapped press should create intended pitch")
        state.ingest(MicroInputEvent(
            identifier: descriptor.identifier,
            kind: .key,
            value: 0,
            phase: .released,
            timestamp: 2,
            controlMapping: .pitch,
            controlScale: 1
        ))
        try expect(state.intended.pitch == 0, "release should clear the mapped intended pitch")
    }

    static func testCodexMicroProfileDoesNotAssumeGenericAxes() throws {
        let axis = HIDElementDescriptor(
            identifier: "micro:axis",
            usagePage: 0x01,
            usage: 0x30,
            isRelative: false
        )
        try expect(BuiltInControlProfiles.codexMicro.action(for: axis) == nil, "Codex Micro axes require report inspection before mapping")
    }
}
