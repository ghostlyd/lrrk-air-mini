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
    let lastReportAt: TimeInterval?
    let maximumConcurrentInputs: Int
    let simultaneousInputSessions: Int
    let now: TimeInterval
    let onResetObservation: () -> Void
    let onAcceptStep: () -> Void
    let onRestart: () -> Void

    @State private var selectedControl: CodexMicroPhysicalControl = .knob
    @State private var hoveredControl: CodexMicroPhysicalControl?
    @State private var stagedAssignments: [CodexMicroPhysicalControl: CodexMicroAssignment] = [:]
    @State private var calibratedStepByControl: [CodexMicroPhysicalControl: String] = [:]

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
               step.kind == .dialClockwise || step.kind == .dialCounterclockwise {
                selectedControl = .knob
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
                Text("Physical reference · hover or click a control to configure it")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text("13 mechanical switches · 1 touch sensor · 1 rotary encoder · 1 planar joystick. K is one visible position with separate press/turn behavior.")
                .font(.caption2)
                .foregroundStyle(.secondary)

            GeometryReader { proxy in
                let side = min(proxy.size.width, proxy.size.height)
                ZStack {
                    RoundedRectangle(cornerRadius: side * 0.045)
                        .fill(Color.black.opacity(0.90))
                    RoundedRectangle(cornerRadius: side * 0.045)
                        .strokeBorder(Color.white.opacity(0.82), lineWidth: max(1, side * 0.004))
                        .padding(side * 0.012)

                    Image(systemName: "arrow.up")
                        .font(.system(size: side * 0.045, weight: .medium))
                        .foregroundStyle(.white.opacity(0.9))
                        .position(x: side * 0.50, y: side * 0.052)

                    ForEach(CodexMicroPhysicalControl.allCases) { control in
                        physicalControlTile(control)
                            .frame(
                                width: side * CGFloat(control.normalizedSize.width),
                                height: side * CGFloat(control.normalizedSize.height)
                            )
                            .position(
                                x: side * CGFloat(control.normalizedCenter.x),
                                y: side * CGFloat(control.normalizedCenter.y)
                            )
                    }

                    ForEach(0..<4, id: \.self) { index in
                        let points: [(x: Double, y: Double)] = [
                            (0.068, 0.068),
                            (0.932, 0.068),
                            (0.068, 0.932),
                            (0.932, 0.932)
                        ]
                        let point = points[index]
                        Circle()
                            .strokeBorder(Color.white.opacity(0.9), lineWidth: max(1, side * 0.004))
                            .frame(width: side * 0.024, height: side * 0.024)
                            .position(x: side * CGFloat(point.x), y: side * CGFloat(point.y))
                    }

                    VStack {
                        Spacer()
                        Text("Work Louder · Codex Micro")
                            .font(.system(size: side * 0.025, weight: .medium))
                            .foregroundStyle(.white.opacity(0.80))
                            .padding(.bottom, side * 0.028)
                    }
                    .frame(width: side, height: side)
                }
                .frame(width: side, height: side)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .aspectRatio(1, contentMode: .fit)
            .frame(maxWidth: 560)
            .frame(maxWidth: .infinity)

            assignmentInspector

            HStack(spacing: 12) {
                legendItem(color: .orange, text: "Calibrate next")
                legendItem(color: .green, text: "Recent report")
                legendItem(color: .blue, text: "Captured")
                Spacer()
                Text("15 physical positions · HID signatures remain evidence-bound")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
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

            HStack(spacing: 14) {
                evidenceValue("Report age", reportAge)
                evidenceValue("Max simultaneous", "\(maximumConcurrentInputs)")
                evidenceValue("Simultaneous sessions", "\(simultaneousInputSessions)")
                Spacer()
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
                        Text("Physical target: \(promptedControl?.label ?? selectedControl.label)")
                            .font(.callout.bold())
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
                    Button("Accept & continue") {
                        let target = step.kind == .dialClockwise || step.kind == .dialCounterclockwise
                            ? CodexMicroPhysicalControl.knob
                            : selectedControl
                        calibratedStepByControl[target] = step.id
                        onAcceptStep()
                    }
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

    private func physicalControlTile(_ control: CodexMicroPhysicalControl) -> some View {
        let target = promptedControl == control
        let captured = calibratedStepByControl[control] != nil
        let observed = recentEvent(for: control) != nil
        let focused = selectedControl == control
        let hovering = hoveredControl == control
        let assignment = stagedAssignments[control] ?? .unassigned

        return Button {
            selectedControl = control
            if let step = captureState.currentStep, step.kind == .buttonOrKey {
                // This records only which tile the operator is calibrating in
                // the UI. The raw HID signature remains learned separately.
                calibratedStepByControl[control] = step.id
            }
        } label: {
            ZStack {
                physicalShape(
                    control,
                    fill: tileFill(target: target, accepted: captured, observed: observed, focused: focused)
                )

                if control == .knob {
                    Rectangle()
                        .fill(Color.white.opacity(0.72))
                        .frame(height: 1.5)
                        .padding(.horizontal, 6)
                } else if control == .topRightPlanarJoystick {
                    directionalGlyph
                } else if control == .bottomWide {
                    Capsule()
                        .strokeBorder(Color.white.opacity(0.75), lineWidth: 1.5)
                        .padding(8)
                } else {
                    Text(control.shortLabel)
                        .font(.system(.caption, design: .monospaced).bold())
                        .foregroundStyle(.white.opacity(0.92))
                }

                if assignment != .unassigned {
                    VStack {
                        Spacer()
                        Text(assignment.shortLabel)
                            .font(.system(size: 8, weight: .bold, design: .rounded))
                            .foregroundStyle(.white.opacity(0.9))
                            .padding(.bottom, 3)
                    }
                }

                if observed {
                    Circle()
                        .fill(.green)
                        .frame(width: 8, height: 8)
                        .overlay(Circle().strokeBorder(.white.opacity(0.8), lineWidth: 1))
                        .offset(x: 18, y: -18)
                }
            }
            .overlay {
                if hovering {
                    RoundedRectangle(cornerRadius: 10)
                        .strokeBorder(.white.opacity(0.95), lineWidth: 2)
                }
            }
        }
        .buttonStyle(.plain)
        .onHover { isHovering in
            if isHovering {
                hoveredControl = control
            } else if hoveredControl == control {
                hoveredControl = nil
            }
        }
        .help(target ? "Calibrate \(control.label) next" : "Configure \(control.label)")
    }

    @ViewBuilder
    private func physicalShape(_ control: CodexMicroPhysicalControl, fill: Color) -> some View {
        switch control.shape {
        case .knob:
            Circle()
                .fill(fill)
                .overlay(Circle().strokeBorder(Color.white.opacity(0.9), lineWidth: 1.5))
        case .directional:
            Circle()
                .fill(fill)
                .overlay(Circle().strokeBorder(Color.white.opacity(0.9), lineWidth: 1.5))
        case .small:
            Circle()
                .fill(fill)
                .overlay(Circle().strokeBorder(Color.white.opacity(0.9), lineWidth: 1.5))
        case .wide:
            RoundedRectangle(cornerRadius: 12)
                .fill(fill)
                .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Color.white.opacity(0.9), lineWidth: 1.5))
        case .key:
            RoundedRectangle(cornerRadius: 10)
                .fill(fill)
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Color.white.opacity(0.9), lineWidth: 1.5))
        }
    }

    private var directionalGlyph: some View {
        ZStack {
            Image(systemName: "chevron.up")
                .offset(y: -7)
            Image(systemName: "chevron.down")
                .offset(y: 7)
            Image(systemName: "chevron.left")
                .offset(x: -7)
            Image(systemName: "chevron.right")
                .offset(x: 7)
        }
        .font(.system(size: 9, weight: .semibold))
        .foregroundStyle(.white.opacity(0.85))
    }

    @ViewBuilder
    private var assignmentInspector: some View {
        let control = hoveredControl ?? selectedControl
        let assignment = stagedAssignments[control] ?? .unassigned

        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Image(systemName: control.isKnob ? "dial.medium" : "cursorarrow.click.2")
                    .foregroundStyle(control.isKnob ? .orange : .blue)
                VStack(alignment: .leading, spacing: 2) {
                    Text(control.label)
                        .font(.callout.bold())
                    Text(control.isKnob
                         ? "K turn: 360° rotation or vertical up/down; K press is captured separately"
                         : "Choose a staged intent; 360° rotation is disabled here")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Menu {
                    ForEach(CodexMicroAssignment.allCases) { option in
                        Button {
                            setAssignment(option, for: control)
                        } label: {
                            HStack {
                                Text(option.label)
                                if option == assignment {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                        .disabled(!option.isAllowed(on: control))
                    }
                } label: {
                    Label(assignment.label, systemImage: "slider.horizontal.3")
                }
                .menuStyle(.borderlessButton)
            }

            if control.isKnob {
                Label("360° rotation is available only on K and is not transmitted in this read-only stage.", systemImage: "lock.shield")
                    .font(.caption2)
                    .foregroundStyle(.orange)
            }
        }
        .padding(10)
        .background(Color.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10))
    }

    private func setAssignment(_ assignment: CodexMicroAssignment, for control: CodexMicroPhysicalControl) {
        guard assignment.isAllowed(on: control) else { return }
        stagedAssignments[control] = assignment
    }

    private func legendItem(color: Color, text: String) -> some View {
        HStack(spacing: 4) {
            Circle()
                .fill(color)
                .frame(width: 7, height: 7)
            Text(text)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
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

    private var reportAge: String {
        guard let lastReportAt else { return "—" }
        return String(format: "%.2f s", max(0, now - lastReportAt))
    }

    private var latestEvent: ObservedHIDEvent? {
        events.first { event in
            event.event.timestamp <= now && now - event.event.timestamp < 3.0
        }
    }

    private func recentEvent(for control: CodexMicroPhysicalControl) -> ObservedHIDEvent? {
        guard let stepID = calibratedStepByControl[control]
                ?? (promptedControl == control ? captureState.currentStep?.id : nil) else {
            return nil
        }
        let signature = captureState.acceptedSignatureByStep[stepID]
            ?? (captureState.currentStep?.id == stepID ? captureState.currentEvidence.signature : nil)
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

    private var promptedControl: CodexMicroPhysicalControl? {
        guard captureState.currentStep != nil else { return nil }
        if let step = captureState.currentStep,
           step.kind == .dialClockwise || step.kind == .dialCounterclockwise {
            return .knob
        }
        return selectedControl
    }
}
