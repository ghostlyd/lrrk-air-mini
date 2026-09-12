import Foundation

public enum GuidedCaptureKind: String, Equatable, Sendable {
    case buttonOrKey
    case dialClockwise
    case dialCounterclockwise
}

public struct GuidedCaptureStep: Identifiable, Equatable, Sendable {
    public let id: String
    public let label: String
    public let instruction: String
    public let kind: GuidedCaptureKind

    public init(id: String, label: String, instruction: String, kind: GuidedCaptureKind) {
        self.id = id
        self.label = label
        self.instruction = instruction
        self.kind = kind
    }
}

public struct GuidedCapturePlan: Equatable, Sendable {
    public let name: String
    public let diagram: String
    public let steps: [GuidedCaptureStep]

    public init(name: String, diagram: String, steps: [GuidedCaptureStep]) {
        self.name = name
        self.diagram = diagram
        self.steps = steps
    }

    /// The current Codex Micro descriptor exposes five HID button usages and
    /// a relative dial-like input. The physical correlation is still learned
    /// from repeated live reports instead of being inferred from positions or
    /// axes. The diagram is a physical reference for the calibration surface;
    /// its neutral labels are not HID mappings.
    public static let codexMicro = GuidedCapturePlan(
        name: "Codex Micro guided capture",
        diagram: """
        Codex Micro physical reference (USB-C)
                         ↑
        ┌─────────────────────────────────────┐
        │  K   │ T1 │ T2 │ JS                  │
        │ M1   │ M2 │ M3 │ M4                  │
        │ L1   │ L2 │ L3 │ L4                  │
        │ TS   │       BW       │ BR           │
        └─────────────────────────────────────┘

        Select a physical position, then follow the raw-report prompt.
        K is the only position eligible for 360° rotation; it may instead
        be assigned vertical up/down. Position labels do not infer HID axes.
        """,
        steps: [
            GuidedCaptureStep(id: "button-1", label: "Raw button signature 1", instruction: "Select the physical position being calibrated, then press and hold it three times. Release fully between cycles.", kind: .buttonOrKey),
            GuidedCaptureStep(id: "button-2", label: "Raw button signature 2", instruction: "Select the next physical position, then press and hold it three times. Release fully between cycles.", kind: .buttonOrKey),
            GuidedCaptureStep(id: "button-3", label: "Raw button signature 3", instruction: "Select the next physical position, then press and hold it three times. Release fully between cycles.", kind: .buttonOrKey),
            GuidedCaptureStep(id: "button-4", label: "Raw button signature 4", instruction: "Select the next physical position, then press and hold it three times. Release fully between cycles.", kind: .buttonOrKey),
            GuidedCaptureStep(id: "button-5", label: "Raw button signature 5", instruction: "Select the next physical position, then press and hold it three times. Release fully between cycles.", kind: .buttonOrKey),
            GuidedCaptureStep(id: "dial-clockwise", label: "Knob clockwise", instruction: "Select K (top-left knob), then turn it clockwise through at least three distinct detents and stop.", kind: .dialClockwise),
            GuidedCaptureStep(id: "dial-counterclockwise", label: "Knob counter-clockwise", instruction: "Turn K (top-left knob) counter-clockwise through at least three distinct detents and stop.", kind: .dialCounterclockwise),
        ]
    )

    public static let magicKeyboard = GuidedCapturePlan(
        name: "Apple Magic Keyboard guided capture",
        diagram: """
        Apple Magic Keyboard

        ┌────┬────┬────┬────┐  ┌────┬────┐  ┌────┬────┐  ┌─────┐
        │ W  │ A  │ S  │ D  │  │ Q  │ E  │  │ R  │ F  │  │ ESC │
        └────┴────┴────┴────┘  └────┴────┘  └────┴────┘  └─────┘

        Press order: W → S → A → D → Q → E → R → F → Escape
        """,
        steps: [
            keyboardStep(id: "key-w", label: "W", instruction: "Press and hold W three times. Release fully between cycles."),
            keyboardStep(id: "key-s", label: "S", instruction: "Press and hold S three times. Release fully between cycles."),
            keyboardStep(id: "key-a", label: "A", instruction: "Press and hold A three times. Release fully between cycles."),
            keyboardStep(id: "key-d", label: "D", instruction: "Press and hold D three times. Release fully between cycles."),
            keyboardStep(id: "key-q", label: "Q", instruction: "Press and hold Q three times. Release fully between cycles."),
            keyboardStep(id: "key-e", label: "E", instruction: "Press and hold E three times. Release fully between cycles."),
            keyboardStep(id: "key-r", label: "R", instruction: "Press and hold R three times. Release fully between cycles."),
            keyboardStep(id: "key-f", label: "F", instruction: "Press and hold F three times. Release fully between cycles."),
            keyboardStep(id: "key-escape", label: "Escape", instruction: "Press and hold Escape three times. Release fully between cycles.")
        ]
    )

    private static func keyboardStep(id: String, label: String, instruction: String) -> GuidedCaptureStep {
        GuidedCaptureStep(id: id, label: label, instruction: instruction, kind: .buttonOrKey)
    }
}

public struct HIDCaptureSignature: Hashable, Equatable, Sendable {
    public let usagePage: UInt32
    public let usage: UInt32
    public let isRelative: Bool

    public init(usagePage: UInt32, usage: UInt32, isRelative: Bool) {
        self.usagePage = usagePage
        self.usage = usage
        self.isRelative = isRelative
    }
}

public struct GuidedCaptureEvidence: Equatable, Sendable {
    public private(set) var signature: HIDCaptureSignature?
    public private(set) var pressCount = 0
    public private(set) var holdCount = 0
    public private(set) var releaseCount = 0
    public private(set) var positiveDialCount = 0
    public private(set) var negativeDialCount = 0
    public private(set) var rawReports: [String] = []

    public init() {}

    public var observationCount: Int {
        pressCount + holdCount + releaseCount + positiveDialCount + negativeDialCount
    }

    public var observedDialSign: Int? {
        if positiveDialCount > 0 && negativeDialCount == 0 { return 1 }
        if negativeDialCount > 0 && positiveDialCount == 0 { return -1 }
        return nil
    }

    public func meetsHighConfidence(for kind: GuidedCaptureKind) -> Bool {
        switch kind {
        case .buttonOrKey:
            return pressCount >= 3 && holdCount >= 1 && releaseCount >= 3 && rawReports.count >= 3
        case .dialClockwise, .dialCounterclockwise:
            return (positiveDialCount >= 3 || negativeDialCount >= 3) && observedDialSign != nil
        }
    }

    public mutating func record(
        signature: HIDCaptureSignature,
        event: MicroInputEvent,
        rawReport: String
    ) {
        if let existing = self.signature, existing != signature { return }
        self.signature = signature

        switch event.phase {
        case .pressed:
            pressCount += 1
        case .held:
            holdCount += 1
        case .released:
            releaseCount += 1
        case .dial:
            if event.value > 0 { positiveDialCount += 1 }
            if event.value < 0 { negativeDialCount += 1 }
        case .value:
            break
        }

        if rawReport != "—" && rawReports.last != rawReport {
            rawReports.append(rawReport)
            if rawReports.count > 12 { rawReports.removeFirst(rawReports.count - 12) }
        }
    }
}

public struct GuidedCaptureState: Equatable, Sendable {
    public private(set) var plan: GuidedCapturePlan
    public private(set) var stepIndex = 0
    public private(set) var evidenceByStep: [String: GuidedCaptureEvidence] = [:]
    public private(set) var acceptedSignatureByStep: [String: HIDCaptureSignature] = [:]
    public private(set) var dialSignature: HIDCaptureSignature?
    public private(set) var dialSignByStep: [String: Int] = [:]

    private var currentCandidate: HIDCaptureSignature?

    public init(plan: GuidedCapturePlan) {
        self.plan = plan
    }

    public var isComplete: Bool { stepIndex >= plan.steps.count }

    public var currentStep: GuidedCaptureStep? {
        guard stepIndex < plan.steps.count else { return nil }
        return plan.steps[stepIndex]
    }

    public var currentEvidence: GuidedCaptureEvidence {
        guard let step = currentStep else { return GuidedCaptureEvidence() }
        return evidenceByStep[step.id] ?? GuidedCaptureEvidence()
    }

    public var currentCandidateSignature: HIDCaptureSignature? { currentCandidate }

    public var currentStepHighConfidence: Bool {
        guard let step = currentStep else { return false }
        guard currentEvidence.meetsHighConfidence(for: step.kind) else { return false }
        if step.kind == .dialCounterclockwise {
            return currentEvidence.signature == dialSignature
        }
        return true
    }

    public mutating func ingest(
        descriptor: HIDElementDescriptor,
        event: MicroInputEvent,
        rawReport: String
    ) {
        guard let step = currentStep else { return }
        let signature = HIDCaptureSignature(
            usagePage: descriptor.usagePage,
            usage: descriptor.usage,
            isRelative: descriptor.isRelative
        )

        switch step.kind {
        case .buttonOrKey:
            guard event.kind == .button || event.kind == .key else { return }
        case .dialClockwise, .dialCounterclockwise:
            guard event.kind == .dial, event.value != 0 else { return }
            if step.kind == .dialCounterclockwise, let dialSignature, signature != dialSignature {
                return
            }
        }

        if currentCandidate == nil {
            guard !acceptedSignatureByStep.values.contains(signature) || step.kind != .buttonOrKey else { return }
            currentCandidate = signature
        }
        guard currentCandidate == signature else { return }

        var evidence = evidenceByStep[step.id] ?? GuidedCaptureEvidence()
        evidence.record(signature: signature, event: event, rawReport: rawReport)
        evidenceByStep[step.id] = evidence
    }

    @discardableResult
    public mutating func acceptCurrentStep() -> Bool {
        guard let step = currentStep, currentStepHighConfidence,
              let signature = currentEvidence.signature else { return false }
        acceptedSignatureByStep[step.id] = signature
        if step.kind == .dialClockwise {
            dialSignature = signature
        }
        if let dialSign = currentEvidence.observedDialSign {
            dialSignByStep[step.id] = dialSign
        }
        stepIndex += 1
        currentCandidate = nil
        return true
    }

    public mutating func resetCurrentObservation() {
        guard let step = currentStep else { return }
        evidenceByStep.removeValue(forKey: step.id)
        currentCandidate = nil
    }

    public mutating func reset() {
        stepIndex = 0
        evidenceByStep.removeAll(keepingCapacity: true)
        acceptedSignatureByStep.removeAll(keepingCapacity: true)
        dialSignature = nil
        dialSignByStep.removeAll(keepingCapacity: true)
        currentCandidate = nil
    }
}
