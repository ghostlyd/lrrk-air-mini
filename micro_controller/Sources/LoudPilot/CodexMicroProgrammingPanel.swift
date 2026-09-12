import Foundation
import LoudPilotCore
import SwiftUI

/// The visual programming surface for the Codex Micro.
///
/// This is intentionally an observation/configuration surface. Selecting a
/// tile changes only the UI focus; it never creates or transmits a flight
/// command. The amber tile is the next physical control LoudPilot is asking
/// the operator to exercise, while green means a recent matching report was
/// observed.
struct CodexMicroProgrammingPanel: View {
    let captureState: GuidedCaptureState
    let events: [ObservedHIDEvent]
    let selectedDeviceConnected: Bool
    let selectedDeviceError: String?
    let hidTransport: String
    let wifiStatus: String
    let wifiDetail: String
    let wifiAvailable: Bool
    let telemetryStatus: String
    let telemetryAge: String
    let battery: String
    let intended: IntendedControlValues
    let mappingSummary: String?
    let reportCount: Int
    let lastReportHex: String
    let now: TimeInterval
    let onResetObservation: () -> Void
    let onAcceptStep: () -> Void
    let onRestart: () -> Void

    @State private var selectedControl: CodexMicroControl = .button1

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            statusRows
            controlSurface
            liveTelemetry
            captureActions
        }
        .padding(16)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 16))
        .overlay {
            RoundedRectangle(cornerRadius: 16)
                .strokeBorder(Color.secondary.opacity(0.24), lineWidth: 1)
        }
        .onChange(of: captureState.stepIndex) { _ in
            if let step = captureState.currentStep,
               let control = CodexMicroControl(stepID: step.id) {
                selectedControl = control
            }
        }
    }

    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Codex Micro")
                    .font(.title2.bold())
                Text("Interactive input configuration")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            statusBadge(
                label: "Capture",
                value: mappingSummary != nil ? "MAPPED · STAGED" : "STEP \(min(captureState.stepIndex + 1, captureState.plan.steps.count))/\(captureState.plan.steps.count)",
                color: mappingSummary != nil ? .green : .orange
            )
        }
    }

    private var statusRows: some View {
        VStack(spacing: 0) {
            statusRow(
                label: "Connection",
                detail: selectedDeviceConnected ? "Codex Micro HID stream over \(hidTransport)" : "Connect the Micro over USB-C",
                value: selectedDeviceConnected ? (hidTransport.uppercased().contains("USB") ? "USB-C" : "Connected") : "Not connected",
                color: selectedDeviceConnected ? .green : .secondary,
                systemImage: selectedDeviceConnected ? "checkmark.circle.fill" : "circle.dashed"
            )
            Divider()
            statusRow(
                label: "Mac Wi-Fi tether",
                detail: wifiDetail,
                value: wifiStatus,
                color: wifiAvailable ? .green : .orange,
                systemImage: wifiAvailable ? "wifi" : "wifi.slash"
            )
            Divider()
            statusRow(
                label: "HID access",
                detail: inputMonitoringDetail,
                value: inputMonitoringValue,
                color: inputMonitoringColor,
                systemImage: inputMonitoringValue == "Granted" ? "checkmark.shield.fill" : "lock.fill"
            )
            Divider()
            statusRow(
                label: "Output boundary",
                detail: "Intended values are displayed only; flight-command transport is disconnected.",
                value: "Read-only",
                color: .green,
                systemImage: "lock.shield.fill"
            )
            Divider()
            statusRow(
                label: "LiteWing telemetry",
                detail: "Age \(telemetryAge) · battery \(battery)",
                value: telemetryStatus,
                color: telemetryStatus == "Streaming" ? .green : .secondary,
                systemImage: "antenna.radiowaves.left.and.right"
            )
        }
        .padding(.horizontal, 10)
        .background(Color.primary.opacity(0.045), in: RoundedRectangle(cornerRadius: 12))
    }

    private var controlSurface: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Layout")
                    .font(.headline)
                Spacer()
                Text("Tap a tile to focus it; follow the amber prompt on the physical Micro.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .center, spacing: 10) {
                controlTile(.dial)
                controlTile(.button1)
                controlTile(.button2)
                controlTile(.button3)
            }
            HStack(alignment: .center, spacing: 10) {
                controlTile(.button4)
                controlTile(.button5)
                Spacer(minLength: 0)
                VStack(alignment: .trailing, spacing: 3) {
                    Text("Physical controls")
                        .font(.caption.bold())
                    Text("5 buttons · 1 dial")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("No joystick axes inferred")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .background(Color.primary.opacity(0.055), in: RoundedRectangle(cornerRadius: 12))
    }

    private var liveTelemetry: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Live input telemetry", systemImage: "waveform.path.ecg")
                    .font(.headline)
                Spacer()
                Text("\(reportCount) raw reports")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .top, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Latest physical event")
                        .font(.caption.bold())
                    if let event = latestEvent {
                        Text(eventLabel(event))
                            .font(.callout.bold())
                            .foregroundStyle(.green)
                        Text("usage \(event.usagePage):\(event.usage) · age \(eventAge(event))")
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    } else {
                        Text("Waiting for a physical report")
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Intended values")
                        .font(.caption.bold())
                    HStack(spacing: 12) {
                        compactValue("R", intended.roll)
                        compactValue("P", intended.pitch)
                        compactValue("Y", intended.yaw)
                        compactValue("T", intended.thrust)
                    }
                    Text("not transmitted")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            Text("Last raw HID report: \(lastReportHex)")
                .font(.system(.caption2, design: .monospaced))
                .lineLimit(2)
                .textSelection(.enabled)
                .foregroundStyle(.secondary)
        }
        .padding(12)
        .background(Color.primary.opacity(0.045), in: RoundedRectangle(cornerRadius: 12))
    }

    @ViewBuilder
    private var captureActions: some View {
        if let step = captureState.currentStep {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "hand.tap.fill")
                        .foregroundStyle(.orange)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("Configure next: \(step.label)")
                            .font(.headline)
                        Text(step.instruction)
                            .font(.callout)
                    }
                }

                let evidence = captureState.currentEvidence
                HStack(spacing: 16) {
                    evidenceValue("Press", "\(evidence.pressCount)")
                    evidenceValue("Hold", "\(evidence.holdCount)")
                    evidenceValue("Release", "\(evidence.releaseCount)")
                    evidenceValue("Raw", "\(evidence.rawReports.count)")
                    if step.kind != .buttonOrKey {
                        evidenceValue("Dial + / −", "\(evidence.positiveDialCount) / \(evidence.negativeDialCount)")
                    }
                    Spacer()
                    Button("Reset") { onResetObservation() }
                    Button("Accept & continue") { onAcceptStep() }
                        .buttonStyle(.borderedProminent)
                        .disabled(!captureState.currentStepHighConfidence)
                }

                if captureState.currentStepHighConfidence {
                    Text("High-confidence evidence is ready. Accept only after the physical control and signature agree.")
                        .font(.caption)
                        .foregroundStyle(.green)
                } else {
                    Text("The amber tile stays active until repeated press/hold/release evidence is captured.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        } else {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: "checkmark.seal.fill")
                        .foregroundStyle(.green)
                    Text(mappingSummary == nil ? "All signatures captured; mapping review is still required." : "All signatures captured. Mapping is staged for review; no flight packet is enabled.")
                        .font(.callout)
                    Spacer()
                    Button("Restart capture") { onRestart() }
                }
                if let mappingSummary {
                    Text(mappingSummary)
                        .font(.system(.caption, design: .monospaced))
                    Text("This stage intentionally leaves thrust unbound and does not transmit flight commands.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func controlTile(_ control: CodexMicroControl) -> some View {
        let target = captureState.currentStep?.id == control.stepID
        let accepted = captureState.acceptedSignatureByStep[control.stepID] != nil
        let observed = recentEvent(for: control) != nil
        let focused = selectedControl == control

        return Button {
            selectedControl = control
        } label: {
            VStack(spacing: 6) {
                ZStack {
                    RoundedRectangle(cornerRadius: control == .dial ? 22 : 10)
                        .fill(tileFill(target: target, accepted: accepted, observed: observed, focused: focused))
                    if control == .dial {
                        Circle()
                            .strokeBorder(Color.primary.opacity(0.30), lineWidth: 2)
                            .padding(10)
                        Image(systemName: "dial.medium")
                            .font(.title2)
                    } else {
                        Text(control.shortLabel)
                            .font(.headline.monospacedDigit())
                    }
                    if observed {
                        Circle()
                            .fill(.green)
                            .frame(width: 8, height: 8)
                            .offset(x: 22, y: -22)
                    }
                }
                .frame(width: 72, height: 58)
                Text(control.label)
                    .font(.caption2)
                    .foregroundStyle(target ? .orange : .secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(6)
            .overlay {
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(focused ? Color.accentColor : .clear, lineWidth: 2)
            }
        }
        .buttonStyle(.plain)
        .help(target ? "Next physical control: \(control.label)" : "Focus \(control.label)")
    }

    private func tileFill(target: Bool, accepted: Bool, observed: Bool, focused: Bool) -> Color {
        if observed { return .green.opacity(0.34) }
        if target { return .orange.opacity(0.32) }
        if accepted { return .blue.opacity(0.30) }
        if focused { return .blue.opacity(0.16) }
        return Color.primary.opacity(0.08)
    }

    private func statusRow(
        label: String,
        detail: String,
        value: String,
        color: Color,
        systemImage: String
    ) -> some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: systemImage)
                .foregroundStyle(color)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 2) {
                Text(label)
                    .font(.callout.bold())
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Text(value)
                .font(.callout.bold())
                .foregroundStyle(color)
        }
        .padding(.vertical, 9)
    }

    private func statusBadge(label: String, value: String, color: Color) -> some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.bold())
                .foregroundStyle(color)
        }
    }

    private func compactValue(_ label: String, _ value: Double) -> some View {
        VStack(spacing: 2) {
            Text(label)
                .font(.caption2.bold())
                .foregroundStyle(.secondary)
            Text(String(format: "%+.2f", value))
                .font(.system(.caption, design: .monospaced).bold())
        }
    }

    private func evidenceValue(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.bold().monospacedDigit())
        }
    }

    private var inputMonitoringValue: String {
        if selectedDeviceConnected && selectedDeviceError == nil { return "Granted" }
        if selectedDeviceError?.contains("e00002e2") == true { return "Blocked" }
        return "Pending"
    }

    private var inputMonitoringColor: Color {
        switch inputMonitoringValue {
        case "Granted": return .green
        case "Blocked": return .red
        default: return .orange
        }
    }

    private var inputMonitoringDetail: String {
        if inputMonitoringValue == "Granted" { return "Raw HID reports can be observed locally" }
        if inputMonitoringValue == "Blocked" { return "macOS denied the HID manager; another Micro consumer may still own the device" }
        return "Waiting for the selected Micro to open"
    }

    private var latestEvent: ObservedHIDEvent? {
        events.first { event in
            event.event.timestamp <= now && now - event.event.timestamp < 3.0
        }
    }

    private func recentEvent(for control: CodexMicroControl) -> ObservedHIDEvent? {
        let signature = captureState.acceptedSignatureByStep[control.stepID]
            ?? (captureState.currentStep?.id == control.stepID ? captureState.currentEvidence.signature : nil)
        guard let signature else { return nil }
        return events.first {
            $0.usagePage == signature.usagePage &&
                $0.usage == signature.usage &&
                $0.event.timestamp <= now &&
                now - $0.event.timestamp < 1.2
        }
    }

    private func eventLabel(_ event: ObservedHIDEvent) -> String {
        let phase = event.event.phase.rawValue.uppercased()
        switch event.event.kind {
        case .dial: return "DIAL \(event.event.value > 0 ? "+" : "−") · \(phase)"
        default: return "\(event.event.kind.rawValue.uppercased()) · \(phase)"
        }
    }

    private func eventAge(_ event: ObservedHIDEvent) -> String {
        String(format: "%.2f s", max(0, now - event.event.timestamp))
    }
}

private enum CodexMicroControl: String, CaseIterable, Identifiable, Equatable {
    case dial
    case button1
    case button2
    case button3
    case button4
    case button5

    var id: String { rawValue }

    var stepID: String {
        switch self {
        case .dial: return "dial-clockwise"
        case .button1: return "button-1"
        case .button2: return "button-2"
        case .button3: return "button-3"
        case .button4: return "button-4"
        case .button5: return "button-5"
        }
    }

    var label: String {
        switch self {
        case .dial: return "Dial"
        case .button1: return "Button 1"
        case .button2: return "Button 2"
        case .button3: return "Button 3"
        case .button4: return "Button 4"
        case .button5: return "Button 5"
        }
    }

    var shortLabel: String {
        switch self {
        case .dial: return "↺  ↻"
        case .button1: return "B1"
        case .button2: return "B2"
        case .button3: return "B3"
        case .button4: return "B4"
        case .button5: return "B5"
        }
    }

    init?(stepID: String) {
        switch stepID {
        case "dial-clockwise", "dial-counterclockwise": self = .dial
        case "button-1": self = .button1
        case "button-2": self = .button2
        case "button-3": self = .button3
        case "button-4": self = .button4
        case "button-5": self = .button5
        default: return nil
        }
    }
}
