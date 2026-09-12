import LoudPilotCore

enum InputSafetyTests {
    private static func event(
        _ identifier: String,
        value: Double,
        phase: MicroInputPhase
    ) -> MicroInputEvent {
        MicroInputEvent(
            identifier: identifier,
            kind: .button,
            value: value,
            phase: phase,
            timestamp: 1
        )
    }

    static func testReleaseClearsCorrespondingIntendedCommand() throws {
        var state = InputSafetyState(bindings: [
            "button:roll": InputBinding(control: .roll, scale: 1.0),
        ])
        state.setConnected(true)
        state.ingest(event("button:roll", value: 1, phase: .pressed))
        try expect(state.intended.roll == 1.0, "press should set roll")

        state.ingest(event("button:roll", value: 0, phase: .released))
        try expect(state.intended.roll == 0.0, "release should clear roll")
        try expect(state.activeInputs.isEmpty, "release should clear active input")
    }

    static func testHoldPreservesInputAndSimultaneousInputsAreIndependent() throws {
        var state = InputSafetyState(bindings: [
            "button:roll": InputBinding(control: .roll, scale: 1.0),
            "button:pitch": InputBinding(control: .pitch, scale: -1.0),
        ])
        state.setConnected(true)
        state.ingest(event("button:roll", value: 1, phase: .pressed))
        state.ingest(event("button:pitch", value: 1, phase: .pressed))
        state.ingest(event("button:roll", value: 1, phase: .held))

        try expect(state.intended == IntendedControlValues(roll: 1, pitch: -1), "hold and simultaneous inputs should persist")
        try expect(state.activeInputs == ["button:roll", "button:pitch"], "simultaneous inputs should remain independent")

        state.ingest(event("button:roll", value: 0, phase: .released))
        try expect(state.intended == IntendedControlValues(roll: 0, pitch: -1), "one release should not clear another input")
        try expect(state.activeInputs == ["button:pitch"], "only released input should be removed")
    }

    static func testDialIsTrackedAsRelativeEventWithoutAssumingAnAxis() throws {
        var state = InputSafetyState(bindings: [:])
        state.setConnected(true)
        state.ingest(MicroInputEvent(
            identifier: "dial:1",
            kind: .dial,
            value: 3,
            phase: .dial,
            timestamp: 1
        ))

        try expect(state.lastDialDelta == 3, "dial delta should be retained")
        try expect(state.intended.isZero, "dial should not be treated as a joystick axis")
    }

    static func testDisconnectClearsInputsAndReconnectDoesNotResumeThem() throws {
        var state = InputSafetyState(bindings: [
            "button:roll": InputBinding(control: .roll, scale: 1.0),
        ])
        state.setConnected(true)
        state.ingest(event("button:roll", value: 1, phase: .pressed))
        state.setConnected(false)

        try expect(!state.connected, "disconnect should clear connection")
        try expect(state.activeInputs.isEmpty, "disconnect should clear active inputs")
        try expect(state.intended.isZero, "disconnect should clear intended controls")

        state.setConnected(true)
        try expect(state.intended.isZero, "reconnect should not resume intended controls")
        try expect(state.activeInputs.isEmpty, "reconnect should not resume active inputs")
    }

    static func testFocusLossClearsInputsAndInhibitsControl() throws {
        var state = InputSafetyState(bindings: [
            "button:roll": InputBinding(control: .roll, scale: 1.0),
        ])
        state.setConnected(true)
        state.ingest(event("button:roll", value: 1, phase: .pressed))
        state.setFocused(false)

        try expect(!state.controlInputEnabled, "focus loss should inhibit input")
        try expect(state.intended.isZero, "focus loss should clear intended controls")
        try expect(state.activeInputs.isEmpty, "focus loss should clear active inputs")

        state.setFocused(true)
        try expect(state.intended.isZero, "focus regain should not resume intended controls")
        try expect(state.activeInputs.isEmpty, "focus regain should not resume active inputs")
    }

    static func testEmergencyStopLatchesUntilExplicitClear() throws {
        var state = InputSafetyState(bindings: [
            "button:roll": InputBinding(control: .roll, scale: 1.0),
        ])
        state.setConnected(true)
        state.ingest(event("button:roll", value: 1, phase: .pressed))
        state.stop()

        try expect(state.stopLatched, "emergency stop should latch")
        try expect(!state.controlInputEnabled, "latched stop should inhibit input")
        try expect(state.intended.isZero, "emergency stop should clear intended controls")

        state.ingest(event("button:roll", value: 1, phase: .pressed))
        try expect(state.intended.isZero, "latched stop must reject subsequent input")

        state.clearStop()
        try expect(!state.stopLatched, "explicit clear should release the stop latch")
        try expect(state.intended.isZero, "clearing stop must not restore old input")
        state.ingest(event("button:roll", value: 1, phase: .pressed))
        try expect(state.intended.roll == 1, "new input may be accepted after explicit clear")
    }
}
