import LoudPilotCore

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

    static func testCodexMicroPhysicalLayoutMatchesReferenceAndKeepsRotationKnobOnly() throws {
        try expect(CodexMicroPhysicalControl.allCases.count == 15, "physical reference should expose all 15 control positions")
        try expect(CodexMicroPhysicalControl.knob.shape == .knob, "top-left control should be represented as the knob")
        try expect(CodexMicroPhysicalControl.topRightPlanarJoystick.label.contains("planar joystick"), "top-right control should be labeled as the physical joystick")
        try expect(CodexMicroAssignment.rotate360.isAllowed(on: .knob), "360 degree rotation should be allowed on the knob")
        try expect(!CodexMicroAssignment.rotate360.isAllowed(on: .topCenterLeft), "360 degree rotation must not be allowed on a button")
        try expect(CodexMicroAssignment.verticalUp.isAllowed(on: .knob), "the knob should support vertical-up assignment")
        try expect(CodexMicroAssignment.verticalDown.isAllowed(on: .knob), "the knob should support vertical-down assignment")
        try expect(!CodexMicroAssignment.rollLeft.isAllowed(on: .knob), "the knob should not silently become a generic button")
    }

    static func testCodexMicroLearnedMappingRequiresAllSignaturesAndStagesSafeAssignments() throws {
        var capture = GuidedCaptureState(plan: GuidedCapturePlan.codexMicro)

        for button in 1...5 {
            let descriptor = HIDElementDescriptor(
                identifier: "button:\(button)",
                usagePage: 0x09,
                usage: UInt32(button),
                isRelative: false
            )
            for cycle in 0..<3 {
                capture.ingest(
                    descriptor: descriptor,
                    event: MicroInputEvent(identifier: descriptor.identifier, kind: .button, value: 1, phase: .pressed, timestamp: Double(cycle)),
                    rawReport: "b\(button)-press-\(cycle)"
                )
                capture.ingest(
                    descriptor: descriptor,
                    event: MicroInputEvent(identifier: descriptor.identifier, kind: .button, value: 1, phase: .held, timestamp: Double(cycle) + 0.1),
                    rawReport: "b\(button)-hold-\(cycle)"
                )
                capture.ingest(
                    descriptor: descriptor,
                    event: MicroInputEvent(identifier: descriptor.identifier, kind: .button, value: 0, phase: .released, timestamp: Double(cycle) + 0.2),
                    rawReport: "b\(button)-release-\(cycle)"
                )
            }
            try expect(capture.acceptCurrentStep(), "button \(button) should be accepted")
        }

        let dial = HIDElementDescriptor(identifier: "dial", usagePage: 0x01, usage: 0x38, isRelative: true)
        for index in 0..<3 {
            capture.ingest(
                descriptor: dial,
                event: MicroInputEvent(identifier: "dial", kind: .dial, value: 1, phase: .dial, timestamp: Double(index)),
                rawReport: "cw-\(index)"
            )
        }
        try expect(capture.acceptCurrentStep(), "clockwise dial should be accepted")

        for index in 0..<3 {
            capture.ingest(
                descriptor: dial,
                event: MicroInputEvent(identifier: "dial", kind: .dial, value: -1, phase: .dial, timestamp: Double(index)),
                rawReport: "ccw-\(index)"
            )
        }
        try expect(capture.acceptCurrentStep(), "counter-clockwise dial should be accepted")
        try expect(capture.isComplete, "all seven controls should be accepted")

        let noSimultaneousEvidence = HIDInteractionEvidence()
        try expect(
            CodexMicroMappingPolicy.stagedMapping(from: capture, interactionEvidence: noSimultaneousEvidence) == nil,
            "complete signatures without a simultaneous-input session must not stage a mapping"
        )

        var simultaneousEvidence = HIDInteractionEvidence()
        simultaneousEvidence.observe(MicroInputEvent(
            identifier: "button:1",
            kind: .button,
            value: 1,
            phase: .pressed,
            timestamp: 10
        ))
        simultaneousEvidence.observe(MicroInputEvent(
            identifier: "button:2",
            kind: .button,
            value: 1,
            phase: .pressed,
            timestamp: 10.1
        ))
        guard let mapping = CodexMicroMappingPolicy.stagedMapping(from: capture, interactionEvidence: simultaneousEvidence) else {
            throw TestFailure.assertion("complete capture should produce a staged mapping")
        }
        let profile = mapping.profile
        try expect(profile.action(for: HIDElementDescriptor(identifier: "b1", usagePage: 0x09, usage: 1, isRelative: false)) == .control(.roll, -1), "Button 1 should stage roll left")
        try expect(profile.action(for: HIDElementDescriptor(identifier: "b2", usagePage: 0x09, usage: 2, isRelative: false)) == .control(.roll, 1), "Button 2 should stage roll right")
        try expect(profile.action(for: HIDElementDescriptor(identifier: "b3", usagePage: 0x09, usage: 3, isRelative: false)) == .control(.pitch, 1), "Button 3 should stage pitch forward")
        try expect(profile.action(for: HIDElementDescriptor(identifier: "b4", usagePage: 0x09, usage: 4, isRelative: false)) == .control(.pitch, -1), "Button 4 should stage pitch back")
        try expect(profile.action(for: HIDElementDescriptor(identifier: "b5", usagePage: 0x09, usage: 5, isRelative: false)) == .stop, "Button 5 should stage emergency stop")
        try expect(profile.action(for: HIDElementDescriptor(identifier: "dial", usagePage: 0x01, usage: 0x38, isRelative: true)) == .relativeControl(.yaw, 1), "clockwise dial should stage positive yaw")
        try expect(mapping.summary.contains("thrust unbound"), "staged mapping must declare thrust unbound")
    }
}
