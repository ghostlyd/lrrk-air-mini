import AppKit
import LiteWingMicroControllerCore
import SwiftUI

struct DashboardView: View {
    @StateObject private var hidMonitor = HIDMonitor()
    @StateObject private var telemetry = TelemetryClient()
    @Environment(\.scenePhase) private var scenePhase
    @State private var telemetryHost = "192.168.43.42"
    @State private var telemetryPort = "2390"

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header
                    safetyBoundary
                    captureSection
                    microSection
                    telemetrySection(now: context.date.timeIntervalSince1970)
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
            Text("Codex Micro or Apple Magic Keyboard → LoudPilot → read-only LiteWing telemetry")
                .foregroundStyle(.secondary)
        }
    }

    private var safetyBoundary: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("READ-ONLY PILOT STAGE", systemImage: "lock.shield.fill")
                .font(.headline)
                .foregroundStyle(.orange)
            Text("Flight-command transmission is disabled in the binary. No arm, thrust, setpoint, takeoff, or manual-flight packet exists in this app.")
                .font(.callout)
            HStack(spacing: 18) {
                statusPill(label: "Flight TX", value: "DISABLED", color: .green)
                statusPill(label: "Positioning", value: "UNAVAILABLE", color: .orange)
                statusPill(label: "AI/model loop", value: "NOT USED", color: .green)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 12))
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
                        value: hidMonitor.selectedDeviceConnected ? "CONNECTED" : "NOT CONNECTED",
                        color: hidMonitor.selectedDeviceConnected ? .green : .secondary
                    )
                }

                if hidMonitor.devices.isEmpty {
                    Text("No HID device is currently identified as a Codex Micro or Magic Keyboard. Connect either device over USB-C or Bluetooth; this window will enumerate its metadata and capture its actual reports.")
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
                            if device.isMicroCandidate {
                                Text("Micro candidate")
                                    .font(.caption.bold())
                                    .foregroundStyle(.blue)
                            }
                            Button(hidMonitor.selectedDeviceID == device.id ? "Selected" : "Select") {
                                hidMonitor.selectDevice(id: device.id)
                            }
                            .disabled(hidMonitor.selectedDeviceID == device.id)
                        }
                        .padding(.vertical, 2)
                    }
                }

                Divider()
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
                    valueColumn("Active reports", "\(hidMonitor.safetyState.activeInputs.count)")
                    valueColumn("Raw reports", "\(hidMonitor.reportCount)")
                }

                Text("Intended control values (not transmitted)")
                    .font(.headline)
                Text("Magic Keyboard uses the documented keyboard profile. Codex Micro remains report-review-only until its live button/dial reports are captured; generic HID axes are not assumed to be proportional controls.")
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

    private var captureSection: some View {
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

                Text("Both connected devices are listed below. Select one, then follow the labeled order. LoudPilot binds only repeated live HID signatures; generic joystick axes are never inferred.")
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
                    Text("All guided signatures are captured. Mapping remains staged and disconnected from flight-command transmission until the evidence review and secured-chamber validation are complete.")
                        .foregroundStyle(.green)
                    Button("Restart guided capture") {
                        hidMonitor.resetCaptureSession()
                    }
                }

                if let error = hidMonitor.selectedDeviceError {
                    Text("Capture unavailable for the selected device: \(error). Enable LoudPilot in macOS Input Monitoring, then use Retry.")
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
                    Button("Connect read-only") {
                        guard let port = UInt16(telemetryPort), port > 0 else { return }
                        telemetry.connect(to: TelemetryEndpoint(host: telemetryHost, port: port))
                    }
                    .disabled(telemetry.status != .disconnected && !isFailed)
                    Button("Disconnect") {
                        telemetry.disconnect()
                    }
                    .disabled(telemetry.status == .disconnected)
                }

                Text("Only CRTP log-port discovery and log subscription packets are allowed. No flight-control port is reachable from this client.")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                Divider()
                HStack(alignment: .top, spacing: 30) {
                    valueColumn("Telemetry age", telemetryAge(now: now))
                    valueColumn("Battery", batteryValue)
                    valueColumn("Inbound packets", "\(telemetry.inboundPacketCount)")
                    valueColumn("Log-only TX", "\(telemetry.outboundReadOnlyPacketCount)")
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

                Text("Advertised variables: \(telemetry.discoveredVariables.count) · subscribed read-only blocks: \(telemetry.activeSchemas.count)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text("Last inbound packet: \(telemetry.lastInboundHex)")
                    .font(.system(.caption, design: .monospaced))
                    .textSelection(.enabled)
            }
        }
    }

    private var telemetryColor: Color {
        switch telemetry.status {
        case .streaming: return .green
        case .stale, .subscribing, .discoveringTOC: return .orange
        case .failed: return .red
        default: return .secondary
        }
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
