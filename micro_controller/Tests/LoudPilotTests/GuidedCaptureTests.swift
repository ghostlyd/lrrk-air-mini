import LoudPilotCore

enum GuidedCaptureTests {
    static func testButtonCaptureRequiresRepeatedPressHoldReleaseEvidence() throws {
        var capture = GuidedCaptureState(plan: GuidedCapturePlan(
            name: "test",
            diagram: "test",
            steps: [GuidedCaptureStep(id: "b1", label: "Button 1", instruction: "test", kind: .buttonOrKey)]
        ))
        let descriptor = HIDElementDescriptor(identifier: "button", usagePage: 0x09, usage: 1, isRelative: false)
        let signature = HIDCaptureSignature(usagePage: 0x09, usage: 1, isRelative: false)

        for cycle in 0..<3 {
            capture.ingest(
                descriptor: descriptor,
                event: MicroInputEvent(identifier: "button", kind: .button, value: 1, phase: .pressed, timestamp: Double(cycle)),
                rawReport: "01"
            )
            capture.ingest(
                descriptor: descriptor,
                event: MicroInputEvent(identifier: "button", kind: .button, value: 1, phase: .held, timestamp: Double(cycle) + 0.1),
                rawReport: "02"
            )
            capture.ingest(
                descriptor: descriptor,
                event: MicroInputEvent(identifier: "button", kind: .button, value: 0, phase: .released, timestamp: Double(cycle) + 0.2),
                rawReport: "00"
            )
        }

        try expect(capture.currentEvidence.signature == signature, "button capture should bind to the observed signature")
        try expect(capture.currentStepHighConfidence, "button capture should require repeated press, hold, release, and raw evidence")
        try expect(capture.acceptCurrentStep(), "high-confidence button evidence should be accepted")
        try expect(capture.isComplete, "single-step capture should complete after acceptance")
    }

    static func testDialCaptureKeepsPhysicalDirectionsOnOneSignature() throws {
        var capture = GuidedCaptureState(plan: GuidedCapturePlan(
            name: "test",
            diagram: "test",
            steps: [
                GuidedCaptureStep(id: "cw", label: "Clockwise", instruction: "test", kind: .dialClockwise),
                GuidedCaptureStep(id: "ccw", label: "Counter-clockwise", instruction: "test", kind: .dialCounterclockwise),
            ]
        ))
        let descriptor = HIDElementDescriptor(identifier: "dial", usagePage: 0x01, usage: 0x38, isRelative: true)
        for index in 0..<3 {
            capture.ingest(
                descriptor: descriptor,
                event: MicroInputEvent(identifier: "dial", kind: .dial, value: 1, phase: .dial, timestamp: Double(index)),
                rawReport: "cw\(index)"
            )
        }
        try expect(capture.currentStepHighConfidence, "clockwise capture should accept repeated relative deltas")
        try expect(capture.acceptCurrentStep(), "clockwise evidence should be accepted")

        for index in 0..<3 {
            capture.ingest(
                descriptor: descriptor,
                event: MicroInputEvent(identifier: "dial", kind: .dial, value: -1, phase: .dial, timestamp: Double(index)),
                rawReport: "ccw\(index)"
            )
        }
        try expect(capture.currentStepHighConfidence, "counter-clockwise capture should require the same dial signature")
        try expect(capture.currentEvidence.observedDialSign == -1, "counter-clockwise evidence should retain its observed sign")
    }

    static func testAxesAreIgnoredDuringButtonCapture() throws {
        var capture = GuidedCaptureState(plan: GuidedCapturePlan(
            name: "test",
            diagram: "test",
            steps: [GuidedCaptureStep(id: "b1", label: "Button 1", instruction: "test", kind: .buttonOrKey)]
        ))
        let axis = HIDElementDescriptor(identifier: "axis", usagePage: 0x01, usage: 0x30, isRelative: false)
        capture.ingest(
            descriptor: axis,
            event: MicroInputEvent(identifier: "axis", kind: .axis, value: 127, phase: .value, timestamp: 1),
            rawReport: "axis"
        )
        try expect(capture.currentEvidence.observationCount == 0, "generic axes must not bind a button capture step")
    }
}
