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
            Text("LiteWing Micro Controller")
                .font(.largeTitle.bold())
            Text("Bluetooth Micro monitor → local macOS app → read-only LiteWing telemetry")
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
                    Label("Micro input monitor", systemImage: "dot.radiowaves.left.and.right")
                        .font(.title3.bold())
                    Spacer()
                    statusPill(
                        label: "Bluetooth",
                        value: hidMonitor.selectedDeviceConnected ? "CONNECTED" : "NOT CONNECTED",
                        color: hidMonitor.selectedDeviceConnected ? .green : .secondary
                    )
                }

                if hidMonitor.devices.isEmpty {
                    Text("No HID device is currently identified as a Codex Micro. Connect it over Bluetooth; this window will enumerate its metadata and capture its actual reports.")
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
                HStack(alignment: .top, spacing: 28) {
                    valueColumn("Focus", hidMonitor.safetyState.focused ? "ACTIVE" : "LOST")
                    valueColumn("Control input", hidMonitor.safetyState.controlInputEnabled ? "OBSERVING" : "INHIBITED")
                    valueColumn("Active reports", "\(hidMonitor.safetyState.activeInputs.count)")
                    valueColumn("Raw reports", "\(hidMonitor.reportCount)")
                }

                Text("Intended control values (not transmitted)")
                    .font(.headline)
                Text("No Micro bindings are assumed until the real input reports are inspected. Axes remain raw observations, not joystick commands.")
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
