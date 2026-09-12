import Foundation

@main
struct LiteWingMicroControllerTests {
    static func main() {
        do {
            try InputSafetyTests.testReleaseClearsCorrespondingIntendedCommand()
            try InputSafetyTests.testHoldPreservesInputAndSimultaneousInputsAreIndependent()
            try InputSafetyTests.testDialIsTrackedAsRelativeEventWithoutAssumingAnAxis()
            try InputSafetyTests.testDisconnectClearsInputsAndReconnectDoesNotResumeThem()
            try InputSafetyTests.testFocusLossClearsInputsAndInhibitsControl()
            try HIDInputTests.testButtonPressHoldReleaseLifecycle()
            try HIDInputTests.testDeviceCandidateMatchingUsesMetadataNotJoystickAssumptions()
            try HIDInputTests.testSimultaneousButtonsMaintainIndependentActiveIDs()
            try HIDInputTests.testRelativeWheelIsReportedAsDialAndNotAxis()
            try HIDInputTests.testGenericDesktopAxisIsObservedButNotMappedAsJoystickCommand()
            try ControlMappingTests.testMagicKeyboardProfileMapsObservedKeyUsagesAndEscapeStops()
            try ControlMappingTests.testMappedInputReleaseClearsIntendedValue()
            try ControlMappingTests.testCodexMicroProfileDoesNotAssumeGenericAxes()
            try GuidedCaptureTests.testButtonCaptureRequiresRepeatedPressHoldReleaseEvidence()
            try GuidedCaptureTests.testDialCaptureKeepsPhysicalDirectionsOnOneSignature()
            try GuidedCaptureTests.testAxesAreIgnoredDuringButtonCapture()
            try TelemetryWireTests.testLogTocInfoPacketUsesOnlyTheReadOnlyLogPort()
            try TelemetryWireTests.testFlightControlPortsCannotBeEncoded()
            try TelemetryWireTests.testLogTocItemIsDecodedWithoutInventingMissingValues()
            try TelemetryWireTests.testLogSampleUpdatesBatteryAndIMUAndLeavesPositioningUnavailable()
            try TelemetryWireTests.testFlightCommandTransmissionSurfaceIsAbsent()
            try TelemetryWireTests.testDiscoveryPlanUsesOnlyAdvertisedNonPositioningVariables()
            print("PASS: LiteWingMicroControllerTests")
        } catch {
            fputs("FAIL: \(error)\n", stderr)
            Foundation.exit(1)
        }
    }
}
