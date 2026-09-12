import AppKit
import LoudPilotCore
import SwiftUI

struct DashboardView: View {
    @StateObject private var hidMonitor = HIDMonitor()
    @StateObject private var bluetooth = BluetoothDiscovery()
    @StateObject private var telemetry = TelemetryClient()
    @StateObject private var wifiPath = WiFiPathMonitor()
    @Environment(\.scenePhase) private var scenePhase
    @State private var telemetryHost = "192.168.43.42"
    @State private var telemetryPort = "2390"
    @State private var imuOrientationVerified = false
    @State private var motorOrderVerified = false
    @State private var securedBenchTestsPassed = false
    @State private var operatorOutdoorApproval = false

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header
                    safetyBoundary
                    bluetoothSection
                    captureSection(now: context.date.timeIntervalSince1970)
                    microSection
                    telemetrySection(now: context.date.timeIntervalSince1970)
                    validationSection(now: context.date.timeIntervalSince1970)
                }
                .padding(22)
            }
        }
        .onAppear {
            hidMonitor.start()
            hidMonitor.setFocused(NSApp.isActive)
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didResignActiveNotification)) { _ in
            hidMonitor.setFocused(false)
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            hidMonitor.setFocused(true)
        }
        .onChange(of: scenePhase) { phase in
            if phase != .active {
                hidMonitor.setFocused(false)
            } else {
                hidMonitor.setFocused(true)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("LoudPilot")
                .font(.largeTitle.bold())
            Text("Codex Micro USB-C → LoudPilot → Mac Wi-Fi → LiteWing telemetry")
                .foregroundStyle(.secondary)
        }
    }

    private var safetyBoundary: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("CONTROL PLANE", systemImage: "slider.horizontal.3")
                .font(.headline)
                .foregroundStyle(.orange)
            Text("LoudPilot contains separate input, telemetry, and flight-command paths. Control output starts disconnected and disarmed; only the scoped Codex Micro can feed pilot input.")
                .font(.callout)
            HStack(spacing: 18) {
                statusPill(label: "Flight TX", value: flightOutputGate.canTransmit ? "ENABLED" : "STAGED", color: .orange)
                statusPill(label: "Controller scope", value: "MICRO ONLY", color: .green)
                statusPill(label: "Positioning", value: "UNAVAILABLE", color: .orange)
                statusPill(label: "AI/model loop", value: "NOT USED", color: .green)
                statusPill(
                    label: "Failsafes",
                    value: flightOutputGate.failsafeActive ? "ACTIVE" : "CLEAR",
                    color: flightOutputGate.failsafeActive ? .orange : .green
                )
                statusPill(
                    label: "E-stop",
                    value: hidMonitor.safetyState.stopLatched ? "LATCHED" : "READY",
                    color: hidMonitor.safetyState.stopLatched ? .red : .green
                )
                Spacer()
                Button("EMERGENCY STOP") {
                    hidMonitor.triggerEmergencyStop()
                }
                .buttonStyle(.borderedProminent)
                .tint(.red)
                Button("Clear E-stop") {
                    hidMonitor.clearEmergencyStop()
                }
                .disabled(!hidMonitor.safetyState.stopLatched)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
    }

    private var bluetoothSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label("Bluetooth discovery", systemImage: "dot.radiowaves.left.and.right")
                        .font(.title3.bold())
                    Spacer()
                    statusPill(
                        label: "Bluetooth",
                        value: bluetooth.status.label,
                        color: bluetooth.status == .scanning || bluetooth.status == .poweredOn ? .green : .orange
                    )
                    Button(bluetooth.isScanning ? "Stop" : "Discover") {
                        if bluetooth.isScanning {
                            bluetooth.stop()
                        } else {
                            bluetooth.discover()
                        }
                    }
                }

                Text("Discovery is integrated for controller identification. Only Codex Micro or Work Louder Micro names are eligible for control; Apple Magic Keyboard and other Bluetooth devices remain out of scope.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if bluetooth.peripherals.isEmpty {
                    Text("No Bluetooth peripherals discovered in the last scan.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(bluetooth.peripherals) { peripheral in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(peripheral.name)
                                Text("\(peripheral.id) · RSSI \(peripheral.rssi) dBm")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(peripheral.isControllerCandidate ? "Controller eligible" : "Out of scope")
                                .font(.caption.bold())
                                .foregroundStyle(peripheral.isControllerCandidate ? .green : .secondary)
                        }
                    }
                }

                Text("Eligible Micro devices: \(bluetooth.controllerCandidates.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var microSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label("Physical input monitor", systemImage: "dot.radiowaves.left.and.right")
                        .font(.title3.bold())
                    Spacer()
                    statusPill(
                        label: "Input device",
                        value: hidMonitor.selectedDeviceConnected
                            ? "LOUDPILOT"
                            : (hidMonitor.selectedDeviceID == nil ? "NOT CONNECTED" : "RELEASED"),
                        color: hidMonitor.selectedDeviceConnected ? .green : .orange
                    )
                }

                if hidMonitor.devices.isEmpty {
                    Text("No HID device is currently identified as a Codex Micro or Work Louder Micro. Connect the Micro over USB-C or Bluetooth; other HID devices are never used as pilot input.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(hidMonitor.devices) { device in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(device.product)
                                Text("\(device.manufacturer) · \(device.transport) · VID \(device.vendorID) PID \(device.productID)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if device.isControllerCandidate {
                                Text("Controller eligible")
                                    .font(.caption.bold())
                                    .foregroundStyle(.blue)
                            } else {
                                Text("Out of scope")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Button(hidMonitor.selectedDeviceID == device.id ? "Selected" : "Select") {
                                hidMonitor.selectDevice(id: device.id)
                            }
                            .disabled(!device.isControllerCandidate || hidMonitor.selectedDeviceID == device.id)
                        }
                        .padding(.vertical, 2)
                    }
                }

                Divider()
                HStack(alignment: .top, spacing: 14) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Input ownership")
                            .font(.headline)
                        Text("On seizes the selected Micro for LoudPilot. Off closes it and releases the device so the Codex app can reconnect.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Toggle(
                        "LoudPilot exclusive input",
                        isOn: Binding(
                            get: { hidMonitor.inputOwnershipMode == .exclusive },
                            set: { hidMonitor.setInputOwnershipEnabled($0) }
                        )
                    )
                    .labelsHidden()
                }
                HStack {
                    valueColumn("Ownership", hidMonitor.inputOwnershipMode.label)
                    if hidMonitor.inputOwnershipMode == .exclusive {
                        Text("The Codex app should no longer receive Micro input while this is on.")
                            .font(.caption)
                            .foregroundStyle(.green)
                    } else {
                        Text("LoudPilot is not reading control input.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                HStack {
                    valueColumn("Active profile", hidMonitor.activeProfileName)
                    if let error = hidMonitor.selectedDeviceError {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                        Button("Retry") {
                            hidMonitor.retrySelectedDevice()
                        }
                    }
                }
                HStack(alignment: .top, spacing: 28) {
                    valueColumn("Focus", hidMonitor.safetyState.focused ? "ACTIVE" : "LOST")
                    valueColumn("Control input", hidMonitor.safetyState.controlInputEnabled ? "OBSERVING" : "INHIBITED")
                    valueColumn("E-stop", hidMonitor.safetyState.stopLatched ? "LATCHED" : "READY")
                    valueColumn("Active reports", "\(hidMonitor.safetyState.activeInputs.count)")
                    valueColumn("Dial delta", String(format: "%+.2f", hidMonitor.safetyState.lastDialDelta))
                    valueColumn("Raw reports", "\(hidMonitor.reportCount)")
                }

                Text("Intended control values")
                    .font(.headline)
                Text("Only the selected Codex Micro/Work Louder Micro contributes to these values. Its button and dial mappings are learned from live reports; generic HID axes are not assumed to be proportional controls.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                let intended = hidMonitor.safetyState.intended
                HStack(spacing: 18) {
                    controlValue("Roll", intended.roll)
                    controlValue("Pitch", intended.pitch)
                    controlValue("Yaw", intended.yaw)
                    controlValue("Thrust", intended.thrust)
                }

                Text("Last raw HID report: \(hidMonitor.lastReportHex)")
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)

                if !hidMonitor.events.isEmpty {
                    Text("Observed input events")
                        .font(.headline)
                    ForEach(hidMonitor.events.prefix(12)) { observed in
                        HStack {
                            Text(observed.event.phase.rawValue.uppercased())
                                .font(.caption.bold())
                                .frame(width: 72, alignment: .leading)
                            Text(observed.event.kind.rawValue)
                                .frame(width: 72, alignment: .leading)
                            Text("usage \(observed.usagePage):\(observed.usage)")
                                .font(.system(.caption, design: .monospaced))
                            Spacer()
                            Text(String(format: "%.3f", observed.event.value))
                                .font(.system(.caption, design: .monospaced))
                        }
                        .foregroundStyle(observed.event.phase == .released ? .secondary : .primary)
                    }
                }
            }
        }
    }

    private func captureSection(now: TimeInterval) -> some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label("Guided HID capture", systemImage: "list.number")
                        .font(.title3.bold())
                    Spacer()
                    statusPill(
                        label: "Evidence",
                        value: hidMonitor.captureState.isComplete ? "COMPLETE" : "STEP \(min(hidMonitor.captureState.stepIndex + 1, hidMonitor.captureState.plan.steps.count))/\(hidMonitor.captureState.plan.steps.count)",
                        color: hidMonitor.captureState.isComplete ? .green : .orange
                    )
                }

                CodexMicroProgrammingPanel(
                    captureState: hidMonitor.captureState,
                    events: hidMonitor.events,
                    selectedDeviceConnected: hidMonitor.selectedDeviceConnected,
                    selectedDeviceError: hidMonitor.selectedDeviceError,
                    hidTransport: selectedHIDTransport,
                    wifiStatus: wifiPath.status.label,
                    wifiDetail: wifiDetail,
                    wifiAvailable: wifiPath.status == .connected,
                    telemetryStatus: telemetry.status.label,
                    telemetryAge: telemetryAge(now: now),
                    battery: batteryValue,
                    intended: hidMonitor.safetyState.intended,
                    mappingSummary: hidMonitor.learnedMapping?.summary,
                    reportCount: hidMonitor.reportCount,
                    lastReportHex: hidMonitor.lastReportHex,
                    now: now,
                    onResetObservation: { hidMonitor.resetCaptureObservation() },
                    onAcceptStep: { hidMonitor.acceptCaptureStep() },
                    onRestart: { hidMonitor.resetCaptureSession() }
                )

                Text("Use the selected Micro only and follow the labeled order. LoudPilot binds only repeated live HID signatures; generic joystick axes are never inferred.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Text(hidMonitor.captureState.plan.diagram)
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.gray.opacity(0.10), in: RoundedRectangle(cornerRadius: 8))

                if let step = hidMonitor.captureState.currentStep {
                    HStack(alignment: .top, spacing: 14) {
                        Text("Next")
                            .font(.caption.bold())
                            .foregroundStyle(.orange)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(step.label)
                                .font(.headline)
                            Text(step.instruction)
                        }
                    }

                    let evidence = hidMonitor.captureState.currentEvidence
                    HStack(alignment: .top, spacing: 22) {
                        valueColumn("Presses", "\(evidence.pressCount)")
                        valueColumn("Holds", "\(evidence.holdCount)")
                        valueColumn("Releases", "\(evidence.releaseCount)")
                        valueColumn("Dial + / −", "\(evidence.positiveDialCount) / \(evidence.negativeDialCount)")
                        valueColumn("Raw samples", "\(evidence.rawReports.count)")
                    }

                    if let signature = evidence.signature {
                        Text("Candidate HID signature: usage \(signature.usagePage):\(signature.usage), relative \(signature.isRelative ? "yes" : "no")")
                            .font(.system(.caption, design: .monospaced))
                    }

                    HStack {
                        Button("Reset current observation") {
                            hidMonitor.resetCaptureObservation()
                        }
                        Button("Accept signature and continue") {
                            hidMonitor.acceptCaptureStep()
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(!hidMonitor.captureState.currentStepHighConfidence)
                    }

                    if hidMonitor.captureState.currentStepHighConfidence {
                        Text("High-confidence evidence is ready for review. Accept it before moving to the next control.")
                            .font(.caption)
                            .foregroundStyle(.green)
                    } else {
                        Text("Required evidence: three repeated press/release cycles plus a hold for buttons, or three consistent detents for each dial direction.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } else {
                    Text("All guided signatures are captured. The resulting Micro mapping is available to the control adapter and remains disabled until the explicit output gate is enabled.")
                        .foregroundStyle(.green)
                    Button("Restart guided capture") {
                        hidMonitor.resetCaptureSession()
                    }
                }

                if let error = hidMonitor.selectedDeviceError {
                    Text("Capture unavailable for the selected device: \(error). Release the Micro from any other HID consumer, then use Retry. LoudPilot cannot close another process's HID session.")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
        }
    }

    private func telemetrySection(now: TimeInterval) -> some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Label("LiteWing telemetry", systemImage: "antenna.radiowaves.left.and.right")
                        .font(.title3.bold())
                    Spacer()
                    statusPill(label: "Drone", value: telemetry.status.label, color: telemetryColor)
                }

                HStack {
                    TextField("Drone Wi-Fi host", text: $telemetryHost)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 180)
                    TextField("Port", text: $telemetryPort)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 80)
                    Button("Connect") {
                        guard let port = UInt16(telemetryPort), port > 0 else { return }
                        telemetry.connect(to: TelemetryEndpoint(host: telemetryHost, port: port))
                    }
                    .disabled(telemetry.status != .disconnected && !isFailed)
                    Button("Disconnect") {
                        telemetry.disconnect()
                    }
                    .disabled(telemetry.status == .disconnected)
                }

                Text("Telemetry uses the CRTP log port. Flight-command encoding is a separate control-plane path and is not activated by this telemetry connection.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Text("Output gate: \(flightOutputGate.blockingReasons.joined(separator: " · "))")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Divider()
                HStack(alignment: .top, spacing: 30) {
                    valueColumn("Telemetry age", telemetryAge(now: now))
                    valueColumn("Battery", batteryValue)
                    valueColumn("Inbound packets", "\(telemetry.inboundPacketCount)")
                    valueColumn("Telemetry TX", "\(telemetry.outboundTelemetryPacketCount)")
                }

                HStack {
                    statusPill(
                        label: "Link-loss failsafe",
                        value: telemetry.telemetryFreshness.inhibitsOutput ? "ACTIVE" : "CLEAR (READ-ONLY)",
                        color: telemetry.telemetryFreshness.inhibitsOutput ? .orange : .green
                    )
                    Text("Only fresh decoded sensor data can clear this gate; Wi-Fi reachability and log ACKs do not.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                HStack(alignment: .top, spacing: 24) {
                    telemetryVector("Gyro", telemetry.state.gyro)
                    telemetryVector("Accelerometer", telemetry.state.accelerometer)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Positioning")
                            .font(.caption.bold())
                        Text("Unavailable")
                            .foregroundStyle(.orange)
                        Text("Shield not positively verified")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }

                Text("Advertised variables: \(telemetry.discoveredVariables.count) · subscribed telemetry blocks: \(telemetry.activeSchemas.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Last inbound packet: \(telemetry.lastInboundHex)")
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
            }
        }
    }

    private func validationSection(now: TimeInterval) -> some View {
        let evidence = stagedValidationEvidence(now: now)
        return GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label("Staged validation", systemImage: "checklist")
                        .font(.title3.bold())
                    Spacer()
                    statusPill(
                        label: "Outdoor phase",
                        value: evidence.outdoorPhaseReady ? "READY" : "LOCKED",
                        color: evidence.outdoorPhaseReady ? .green : .orange
                    )
                }

                Text("Outdoor prompting stays locked until read-only capture, telemetry, physical orientation, emergency-stop, and secured-bench evidence are all recorded.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Toggle("IMU orientation physically verified", isOn: $imuOrientationVerified)
                Toggle("Motor corner/order mapping physically verified", isOn: $motorOrderVerified)
                Toggle("Secured-bench tests passed", isOn: $securedBenchTestsPassed)

                if evidence.securedBenchReady {
                    Toggle("Operator outdoor approval", isOn: $operatorOutdoorApproval)
                } else {
                    Text("Missing gates: \(evidence.missingGates.joined(separator: ", "))")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }

                if evidence.outdoorPhaseReady {
                    Text("Outdoor phase is unlocked for a human-reviewed next step. Flight output remains separately gated.")
                        .font(.callout.bold())
                        .foregroundStyle(.green)
                } else {
                    Text("No outdoor prompt is emitted while any gate is missing.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func stagedValidationEvidence(now: TimeInterval) -> StagedValidationEvidence {
        let telemetryAge = telemetry.state.telemetryAge(now: now)
        let telemetryFresh = telemetry.telemetryFreshness == .fresh && telemetryAge.map { $0 <= 2.0 } == true
        return StagedValidationEvidence(
            inputCaptureComplete: hidMonitor.captureState.isComplete,
            mappingStaged: hidMonitor.learnedMapping != nil,
            telemetryFresh: telemetryFresh,
            batteryVerified: telemetry.state.batteryVoltage != nil,
            imuOrientationVerified: imuOrientationVerified,
            motorOrderVerified: motorOrderVerified,
            emergencyStopVerified: hidMonitor.emergencyStopTested,
            securedBenchTestsPassed: securedBenchTestsPassed,
            operatorOutdoorApproval: operatorOutdoorApproval
        )
    }

    private var flightOutputGate: FlightOutputGate {
        FlightOutputGate(
            inputConnected: hidMonitor.selectedDeviceConnected && hidMonitor.inputOwnershipMode == .exclusive,
            appFocused: hidMonitor.safetyState.focused,
            telemetryFreshness: telemetry.telemetryFreshness,
            mappingStaged: hidMonitor.learnedMapping != nil,
            emergencyStopLatched: hidMonitor.safetyState.stopLatched,
            outputTransportConnected: false
        )
    }

    private var telemetryColor: Color {
        switch telemetry.status {
        case .streaming: return .green
        case .stale, .subscribing, .discoveringTOC: return .orange
        case .failed: return .red
        default: return .secondary
        }
    }

    private var selectedHIDTransport: String {
        guard let selectedID = hidMonitor.selectedDeviceID,
              let device = hidMonitor.devices.first(where: { $0.id == selectedID }) else {
            return "Unknown transport"
        }
        return device.transport
    }

    private var wifiDetail: String {
        wifiPath.status == .connected
            ? "Mac Wi-Fi path available; fresh LiteWing telemetry still required"
            : "Join the LiteWing Wi-Fi network on the Mac before connecting telemetry"
    }

    private var isFailed: Bool {
        if case .failed = telemetry.status { return true }
        return false
    }

    private var batteryValue: String {
        guard let voltage = telemetry.state.batteryVoltage else { return "Unavailable" }
        return String(format: "%.2f V", voltage)
    }

    private func telemetryAge(now: TimeInterval) -> String {
        guard let age = telemetry.state.telemetryAge(now: now) else { return "Unavailable" }
        return String(format: "%.1f s", age)
    }

    private func telemetryVector(_ label: String, _ vector: Vector3?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption.bold())
            if let vector {
                Text(String(format: "x %.3f\ny %.3f\nz %.3f", vector.x, vector.y, vector.z))
                    .font(.system(.callout, design: .monospaced))
            } else {
                Text("Unavailable")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(minWidth: 150, alignment: .leading)
    }

    private func statusPill(label: String, value: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.bold())
                .foregroundStyle(color)
        }
    }

    private func valueColumn(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.callout.bold())
        }
    }

    private func controlValue(_ label: String, _ value: Double) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(String(format: "%+.3f", value))
                .font(.system(.callout, design: .monospaced).bold())
        }
        .frame(minWidth: 90, alignment: .leading)
    }
}
