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
    @State private var outputMode: FlightOutputMode = .readOnly
    @State private var emulatorValues = IntendedControlValues()

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header
                    safetyBoundary
                    commandPathSection
                    bluetoothSection
                    workLouderSection
                    captureSection(now: context.date.timeIntervalSince1970)
                    microSection(now: context.date.timeIntervalSince1970)
                    telemetrySection(now: context.date.timeIntervalSince1970)
                    validationSection(now: context.date.timeIntervalSince1970)
                }
                .padding(22)
            }
        }
        .onAppear {
            bluetooth.start()
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

    private var commandPathSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label("Command path", systemImage: "paperplane")
                        .font(.title3.bold())
                    Spacer()
                    statusPill(
                        label: "Mode",
                        value: outputMode == .emulatorPreview ? "EMULATOR · LOCAL" : outputMode.label.uppercased(),
                        color: outputMode == .emulatorPreview ? .green : .orange
                    )
                }

                Picker("Controller path", selection: $outputMode) {
                    ForEach(FlightOutputMode.allCases, id: \.self) { mode in
                        Text(mode.label).tag(mode)
                    }
                }
                .pickerStyle(.segmented)

                Text(outputMode.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if outputMode == .emulatorPreview {
                    if !hidMonitor.selectedDeviceConnected {
                        emulatorController
                    }
                    let command = FlightCommandMapper().command(for: commandPreviewValues)
                    HStack(alignment: .top, spacing: 24) {
                        valueColumn("Roll", String(format: "%+.2f°", command.rollDegrees))
                        valueColumn("Pitch", String(format: "%+.2f°", command.pitchDegrees))
                        valueColumn("Yaw", String(format: "%+.2f°/s", command.yawDegreesPerSecond))
                        valueColumn("Thrust", "\(command.thrust)")
                        Spacer()
                        statusPill(label: "Physical TX", value: "DISCONNECTED", color: .green)
                    }
                    Text(hidMonitor.selectedDeviceConnected
                         ? "Source: Codex Micro intended values"
                         : "Source: local emulator controller (Micro unavailable)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("Emulator frame preview: \(encodedCommandPreview(command))")
                        .font(.system(.caption2, design: .monospaced))
                        .textSelection(.enabled)
                } else {
                    HStack(spacing: 10) {
                        Image(systemName: "lock.shield.fill")
                            .foregroundStyle(.orange)
                        Text("No live LiteWing flight packet is sent. Physical output remains fail-closed behind telemetry, mapping, focus, stop, and transport gates.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var emulatorController: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Label("Emulator controller", systemImage: "gamecontroller")
                    .font(.callout.bold())
                Spacer()
                Button("Release / neutral") {
                    emulatorValues = IntendedControlValues()
                }
                .buttonStyle(.bordered)
            }
            Text("Local mapping exercise only. These buttons change the preview frame and never transmit to LiteWing.")
                .font(.caption2)
                .foregroundStyle(.secondary)
            HStack(spacing: 8) {
                emulatorButton("Roll −", systemImage: "arrow.left") { emulatorValues = IntendedControlValues(roll: -1) }
                emulatorButton("Roll +", systemImage: "arrow.right") { emulatorValues = IntendedControlValues(roll: 1) }
                emulatorButton("Pitch +", systemImage: "arrow.up") { emulatorValues = IntendedControlValues(pitch: 1) }
                emulatorButton("Pitch −", systemImage: "arrow.down") { emulatorValues = IntendedControlValues(pitch: -1) }
            }
            HStack(spacing: 8) {
                emulatorButton("Yaw −", systemImage: "rotate.left") { emulatorValues = IntendedControlValues(yaw: -1) }
                emulatorButton("Yaw +", systemImage: "rotate.right") { emulatorValues = IntendedControlValues(yaw: 1) }
                emulatorButton("Vertical up", systemImage: "arrow.up.to.line") { emulatorValues = IntendedControlValues(thrust: 1) }
                emulatorButton("Vertical down", systemImage: "arrow.down.to.line") { emulatorValues = IntendedControlValues(thrust: 0) }
            }
        }
        .padding(10)
        .background(Color.green.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
    }

    private func emulatorButton(_ title: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(.caption)
        }
        .buttonStyle(.bordered)
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

                HStack(spacing: 8) {
                    Button("Open Bluetooth Settings") {
                        openBluetoothSettings()
                    }
                    Button("Recheck HID") {
                        hidMonitor.rescan()
                    }
                    .buttonStyle(.bordered)
                    Spacer()
                }

                Text("Discovery is integrated for controller identification. Only Codex Micro or Work Louder Micro names are eligible for control; Apple Magic Keyboard and other Bluetooth devices remain out of scope.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Label(
                    "A nearby Bluetooth name is not yet a selectable input device. LoudPilot requires macOS to expose the Micro as HID before it can be selected or read.",
                    systemImage: "info.circle"
                )
                .font(.caption)
                .foregroundStyle(.orange)

                if hidMonitor.devices.filter(\.isControllerCandidate).isEmpty {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("Make the Micro selectable")
                            .font(.caption.bold())
                        Text(bluetooth.controllerCandidates.isEmpty
                             ? "If macOS shows Codex Micro in Nearby Devices, leave that row alone: it is only an advertisement. On the Bluetooth-capable Micro, hold the bottom-left touch sensor for 3 seconds until the underglow turns blue."
                             : "On the Bluetooth-capable Micro, hold the bottom-left touch sensor for 3 seconds until the underglow turns blue.")
                            .font(.caption)
                        Text("Tap the sensor to choose BLE channel 1, 2, or 3, then wait for the pairing light to become solid. Use Work Louder Input for the communication-mode pairing step.")
                            .font(.caption)
                        Label("Click Recheck HID immediately; communication mode exits after a short idle period.", systemImage: "arrow.clockwise")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("For a wired test, use the fourth tap to select wired mode (white underglow), connect a data-capable USB-C cable, then recheck HID.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(9)
                    .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                }

                if bluetooth.peripherals.isEmpty {
                    Text(bluetooth.status == .initializing
                        ? "Waiting for macOS Bluetooth state or authorization. A Nearby Devices entry is not a selectable HID connection."
                        : "No Bluetooth peripherals discovered in the last scan.")
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
                            Text(peripheral.isControllerCandidate ? "Nearby only · waiting for HID" : "Out of scope")
                                .font(.caption.bold())
                                .foregroundStyle(peripheral.isControllerCandidate ? .orange : .secondary)
                        }
                    }
                }

                Text("Nearby Micro advertisements: \(bluetooth.controllerCandidates.count) · HID devices ready: \(hidMonitor.devices.filter(\.isControllerCandidate).count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var workLouderSection: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label("Work Louder Input compatibility", systemImage: "puzzlepiece.extension")
                        .font(.title3.bold())
                    Spacer()
                    statusPill(
                        label: "Companion",
                        value: workLouderInputURL == nil ? "NOT FOUND" : "AVAILABLE",
                        color: workLouderInputURL == nil ? .secondary : .green
                    )
                }

                Text("LoudPilot uses native HID capture and keeps Work Louder Input optional. The companion can configure Codex Micro layers and gestures; LoudPilot owns the separate telemetry and safety boundary.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                HStack {
                    if let workLouderInputURL {
                        Button("Open Work Louder Input") {
                            NSWorkspace.shared.open(workLouderInputURL)
                        }
                        .disabled(hidMonitor.inputOwnershipMode == .exclusive)
                        if hidMonitor.inputOwnershipMode == .exclusive {
                            Text("Release LoudPilot ownership before opening the companion to avoid HID contention.")
                                .font(.caption2)
                                .foregroundStyle(.orange)
                        }
                    } else {
                        Text("Install the official companion separately if you want its device configuration surface.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if let installer = workLouderInputInstallerURL {
                            Button("Open downloaded installer") {
                                NSWorkspace.shared.open(installer)
                            }
                        }
                    }
                    Spacer()
                    Text("No proprietary binary is bundled")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func microSection(now: TimeInterval) -> some View {
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
                    valueColumn("Max simultaneous", "\(hidMonitor.interactionEvidence.maximumConcurrentInputs)")
                    valueColumn("Report age", hidReportAge(now: now))
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
                    lastReportAt: hidMonitor.lastReportAt,
                    maximumConcurrentInputs: hidMonitor.interactionEvidence.maximumConcurrentInputs,
                    simultaneousInputSessions: hidMonitor.interactionEvidence.simultaneousInputSessions,
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
        let telemetryAge = telemetry.state.completeTelemetryAge(now: now)
        let telemetryFresh = telemetry.telemetryFreshness == .fresh && telemetryAge.map { $0 <= 2.0 } == true
        return StagedValidationEvidence(
            inputCaptureComplete: hidMonitor.captureState.isComplete,
            mappingStaged: hidMonitor.learnedMapping != nil,
            telemetryFresh: telemetryFresh,
            batteryVerified: telemetryFresh && telemetry.state.hasCompleteReadOnlyTelemetry,
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

    private var commandPreviewValues: IntendedControlValues {
        if outputMode == .emulatorPreview && !hidMonitor.selectedDeviceConnected {
            return emulatorValues
        }
        return hidMonitor.safetyState.intended
    }

    private var workLouderInputURL: URL? {
        NSWorkspace.shared.urlForApplication(withBundleIdentifier: "it.focusense.input-app")
    }

    private var workLouderInputInstallerURL: URL? {
        let url = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Downloads/input-0.18.3-arm64.dmg")
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    private func openBluetoothSettings() {
        guard let url = URL(string: "x-apple.systempreferences:com.apple.BluetoothSettings") else { return }
        NSWorkspace.shared.open(url)
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
        guard let age = telemetry.state.completeTelemetryAge(now: now) else { return "Unavailable" }
        return String(format: "%.1f s", age)
    }

    private func hidReportAge(now: TimeInterval) -> String {
        guard let lastReportAt = hidMonitor.lastReportAt else { return "Unavailable" }
        return String(format: "%.2f s", max(0, now - lastReportAt))
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

    private func encodedCommandPreview(_ command: FlightCommand) -> String {
        do {
            return try FlightCommandWire.encodeRPYT(command)
                .map { String(format: "%02x", $0) }
                .joined(separator: " ")
        } catch {
            return "unavailable (\(error))"
        }
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
