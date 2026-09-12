import LoudPilotCore

enum SafetyGateTests {
    static func testTelemetryLinkLossInhibitsControlOutput() throws {
        var gate = FlightOutputGate()
        try expect(gate.telemetryFreshness == .unavailable, "output gate must start with telemetry unavailable")
        try expect(gate.failsafeActive, "missing telemetry must activate the link-loss failsafe")
        try expect(!gate.canTransmit, "missing telemetry must inhibit transmission")

        gate.inputConnected = true
        gate.appFocused = true
        gate.mappingStaged = true
        gate.telemetryFreshness = .fresh
        try expect(!gate.canTransmit, "the staged read-only boundary must still block transmission")
        try expect(gate.blockingReasons.contains("flight output transport disconnected"), "read-only boundary must remain explicit")

        gate.telemetryFreshness = .stale
        try expect(gate.failsafeActive, "stale telemetry must reactivate the link-loss failsafe")
        try expect(gate.blockingReasons.contains("telemetry stale"), "stale telemetry must be named as a blocker")
    }

    static func testTelemetryFreshnessOnlyClearsOnSensorData() throws {
        var freshness = TelemetryFreshness.unavailable
        try expect(freshness.inhibitsOutput, "unavailable telemetry must inhibit output")
        freshness = .fresh
        try expect(!freshness.inhibitsOutput, "fresh telemetry may clear the link-loss condition")
        freshness = .stale
        try expect(freshness.inhibitsOutput, "stale telemetry must inhibit output")
    }
}
