import Foundation

@main
struct LoudPilotTests {
    static func main() {
        do {
            try InputSafetyTests.testReleaseClearsCorrespondingIntendedCommand()
            try InputSafetyTests.testHoldPreservesInputAndSimultaneousInputsAreIndependent()
            try InputSafetyTests.testDialIsTrackedAsRelativeEventWithoutAssumingAnAxis()
            try InputSafetyTests.testDisconnectClearsInputsAndReconnectDoesNotResumeThem()
            try InputSafetyTests.testFocusLossClearsInputsAndInhibitsControl()
            try InputSafetyTests.testFocusRegainRequiresReleaseBeforeHeldInputCanReturn()
            try InputSafetyTests.testReconnectRequiresReleaseBeforeHeldInputCanReturn()
            try InputSafetyTests.testEmergencyStopLatchesUntilExplicitClear()
            try HIDInputTests.testButtonPressHoldReleaseLifecycle()
            try HIDInputTests.testInputOwnershipRequiresExplicitExclusiveMode()
            try HIDInputTests.testVendorTelemetryIsNotSurfacedAsPhysicalControl()
            try HIDInputTests.testDeviceCandidateMatchingUsesMetadataNotJoystickAssumptions()
            try HIDInputTests.testSimultaneousButtonsMaintainIndependentActiveIDs()
            try HIDInputTests.testInteractionEvidenceRecordsSimultaneousSessionWithoutTreatingDialAsHeld()
            try HIDInputTests.testRelativeWheelIsReportedAsDialAndNotAxis()
            try HIDInputTests.testGenericDesktopAxisIsObservedButNotMappedAsJoystickCommand()
            try ControlMappingTests.testMagicKeyboardProfileMapsObservedKeyUsagesAndEscapeStops()
            try ControlMappingTests.testMappedInputReleaseClearsIntendedValue()
            try ControlMappingTests.testCodexMicroProfileDoesNotAssumeGenericAxes()
            try ControlMappingTests.testCodexMicroPhysicalLayoutMatchesReferenceAndKeepsRotationKnobOnly()
            try ControlMappingTests.testCodexMicroLearnedMappingRequiresAllSignaturesAndStagesSafeAssignments()
            try ValidationTests.testOutdoorPhaseRequiresEveryGate()
            try SafetyGateTests.testTelemetryLinkLossInhibitsControlOutput()
            try SafetyGateTests.testTelemetryFreshnessOnlyClearsOnSensorData()
            try GuidedCaptureTests.testButtonCaptureRequiresRepeatedPressHoldReleaseEvidence()
            try GuidedCaptureTests.testDialCaptureKeepsPhysicalDirectionsOnOneSignature()
            try GuidedCaptureTests.testAxesAreIgnoredDuringButtonCapture()
            try ControllerScopeTests.testOnlyCodexMicroIsInControllerScope()
            try ControllerScopeTests.testBluetoothDiscoveryRetainsMicroCandidatesAndMarksKeyboardOutOfScope()
            try ControllerScopeTests.testOutOfScopeHIDCannotAcquirePilotProfile()
            try ControllerScopeTests.testCommanderSetpointUsesLiteWingCRTPSetpointPort()
            try ControllerScopeTests.testNormalizedIntentMapsToLiteWingCommanderRange()
            try TelemetryWireTests.testLogTocInfoPacketUsesOnlyTheTelemetryLogPort()
            try TelemetryWireTests.testTelemetryCodecRejectsFlightControlPorts()
            try TelemetryWireTests.testLogTocItemIsDecodedWithoutInventingMissingValues()
            try TelemetryWireTests.testLogSampleUpdatesBatteryAndIMUAndLeavesPositioningUnavailable()
            try TelemetryWireTests.testDiscoveryPlanUsesOnlyAdvertisedNonPositioningVariables()
            print("PASS: LoudPilotTests")
        } catch {
            fputs("FAIL: \(error)\n", stderr)
            Foundation.exit(1)
        }
    }
}
