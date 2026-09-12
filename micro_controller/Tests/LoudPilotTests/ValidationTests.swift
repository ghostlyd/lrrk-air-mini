import LoudPilotCore

enum ValidationTests {
    static func testOutdoorPhaseRequiresEveryGate() throws {
        var evidence = StagedValidationEvidence()
        try expect(!evidence.securedBenchReady, "empty evidence must not pass the secured-bench gate")
        try expect(!evidence.outdoorPhaseReady, "empty evidence must not allow outdoor phase")
        try expect(evidence.missingGates.contains("IMU orientation"), "missing orientation must remain explicit")

        evidence.inputCaptureComplete = true
        evidence.mappingStaged = true
        evidence.telemetryFresh = true
        evidence.batteryVerified = true
        evidence.imuOrientationVerified = true
        evidence.motorOrderVerified = true
        evidence.emergencyStopVerified = true
        evidence.securedBenchTestsPassed = true

        try expect(evidence.securedBenchReady, "all secured-bench evidence should unlock the bench gate")
        try expect(!evidence.outdoorPhaseReady, "operator approval must remain a separate gate")
        try expect(evidence.missingGates == ["operator outdoor approval"], "only outdoor approval should remain missing")

        evidence.operatorOutdoorApproval = true
        try expect(evidence.outdoorPhaseReady, "outdoor phase should unlock only after explicit approval")
        try expect(evidence.missingGates.isEmpty, "complete evidence should have no missing gates")
    }
}
