import Foundation

public struct StagedValidationEvidence: Equatable, Sendable {
    public var inputCaptureComplete: Bool
    public var mappingStaged: Bool
    public var telemetryFresh: Bool
    public var batteryVerified: Bool
    public var imuOrientationVerified: Bool
    public var motorOrderVerified: Bool
    public var emergencyStopVerified: Bool
    public var securedBenchTestsPassed: Bool
    public var operatorOutdoorApproval: Bool

    public init(
        inputCaptureComplete: Bool = false,
        mappingStaged: Bool = false,
        telemetryFresh: Bool = false,
        batteryVerified: Bool = false,
        imuOrientationVerified: Bool = false,
        motorOrderVerified: Bool = false,
        emergencyStopVerified: Bool = false,
        securedBenchTestsPassed: Bool = false,
        operatorOutdoorApproval: Bool = false
    ) {
        self.inputCaptureComplete = inputCaptureComplete
        self.mappingStaged = mappingStaged
        self.telemetryFresh = telemetryFresh
        self.batteryVerified = batteryVerified
        self.imuOrientationVerified = imuOrientationVerified
        self.motorOrderVerified = motorOrderVerified
        self.emergencyStopVerified = emergencyStopVerified
        self.securedBenchTestsPassed = securedBenchTestsPassed
        self.operatorOutdoorApproval = operatorOutdoorApproval
    }

    public var securedBenchReady: Bool {
        inputCaptureComplete &&
            mappingStaged &&
            telemetryFresh &&
            batteryVerified &&
            imuOrientationVerified &&
            motorOrderVerified &&
            emergencyStopVerified &&
            securedBenchTestsPassed
    }

    public var outdoorPhaseReady: Bool {
        securedBenchReady && operatorOutdoorApproval
    }

    public var missingGates: [String] {
        var missing: [String] = []
        if !inputCaptureComplete { missing.append("Codex Micro capture") }
        if !mappingStaged { missing.append("learned mapping") }
        if !telemetryFresh { missing.append("fresh telemetry") }
        if !batteryVerified { missing.append("verified battery") }
        if !imuOrientationVerified { missing.append("IMU orientation") }
        if !motorOrderVerified { missing.append("motor order") }
        if !emergencyStopVerified { missing.append("emergency stop proof") }
        if !securedBenchTestsPassed { missing.append("secured-bench test pass") }
        if securedBenchReady && !operatorOutdoorApproval { missing.append("operator outdoor approval") }
        return missing
    }
}
