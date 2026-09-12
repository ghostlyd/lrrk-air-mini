import Combine
import Foundation
import IOKit.hid
import LoudPilotCore

struct ObservedHIDEvent: Identifiable {
    let id = UUID()
    let event: MicroInputEvent
    let usagePage: UInt32
    let usage: UInt32
    let rawReport: String
}

@MainActor
final class HIDMonitor: NSObject, ObservableObject {
    @Published private(set) var devices: [HIDDeviceSummary] = []
    @Published private(set) var selectedDeviceID: String?
    @Published private(set) var selectedDeviceConnected = false
    @Published private(set) var selectedDeviceError: String?
    @Published private(set) var activeProfileName = "None"
    @Published private(set) var inputOwnershipMode: HIDInputOwnershipMode = .released
    @Published private(set) var reportCount = 0
    @Published private(set) var lastReportHex = "—"
    @Published private(set) var lastReportAt: TimeInterval?
    @Published private(set) var interactionEvidence = HIDInteractionEvidence()
    @Published private(set) var events: [ObservedHIDEvent] = []
    @Published private(set) var safetyState = InputSafetyState(bindings: [:])
    @Published private(set) var captureState = GuidedCaptureState(plan: .codexMicro)
    @Published private(set) var learnedMapping: CodexMicroMapping?
    @Published private(set) var emergencyStopTested = false

    private var manager: IOHIDManager?
    private var managerOpen = false
    private var deviceByID: [String: IOHIDDevice] = [:]
    private var bufferByID: [String: UnsafeMutablePointer<UInt8>] = [:]
    private var interpreterByID: [String: HIDInputInterpreter] = [:]
    private var reportByID: [String: String] = [:]
    private var profileByID: [String: HIDControlProfile] = [:]

    func start() {
        guard manager == nil else { return }
        let created = IOHIDManagerCreate(kCFAllocatorDefault, IOOptionBits(kIOHIDOptionsTypeNone))
        manager = created
        IOHIDManagerSetDeviceMatching(created, nil)

        let context = Unmanaged.passUnretained(self).toOpaque()
        IOHIDManagerRegisterDeviceMatchingCallback(created, hidDeviceMatched, context)
        IOHIDManagerRegisterDeviceRemovalCallback(created, hidDeviceRemoved, context)
        IOHIDManagerScheduleWithRunLoop(created, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)

        // Released mode must remain invisible to the active Codex app: a
        // manager that is opened merely for discovery can still become a
        // competing HID consumer. Keep the manager unopened and enumerate
        // metadata only until the operator explicitly enables LoudPilot.
        guard inputOwnershipMode.allowsLoudPilotInput else {
            enumerateMetadataOnly(created)
            return
        }

        let result = IOHIDManagerOpen(created, IOOptionBits(kIOHIDOptionsTypeNone))
        guard result == kIOReturnSuccess else {
            selectedDeviceError = String(format: "IOHIDManagerOpen failed (0x%08x)", UInt32(bitPattern: result))
            manager = nil
            return
        }
        managerOpen = true
    }

    private func enumerateMetadataOnly(_ manager: IOHIDManager) {
        guard let devices = IOHIDManagerCopyDevices(manager) else { return }
        for case let device as IOHIDDevice in devices as NSSet {
            let summary = summarize(device)
            if !self.devices.contains(where: { $0.id == summary.id }) {
                self.devices.append(summary)
            }
        }
        self.devices.sort { $0.product.localizedCaseInsensitiveCompare($1.product) == .orderedAscending }
        if selectedDeviceID == nil,
           let candidate = self.devices.first(where: \.isControllerCandidate) {
            selectedDeviceID = candidate.id
        }
    }

    func stop() {
        inputOwnershipMode = .released
        safetyState.stop()
        for id in Array(deviceByID.keys) {
            clearDeviceState(id: id)
        }
        guard let manager else { return }
        IOHIDManagerUnscheduleFromRunLoop(manager, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        if managerOpen {
            IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
            managerOpen = false
        }
        self.manager = nil
        safetyState.setConnected(false)
        selectedDeviceConnected = false
        captureState.reset()
        clearActiveInputState()
    }

    /// Claims the selected HID device exclusively for LoudPilot, or releases
    /// it so the Codex app can reconnect. There is deliberately no shared-open
    /// fallback: shared ownership would let both apps react to the same input.
    func setInputOwnershipEnabled(_ enabled: Bool) {
        let requestedMode: HIDInputOwnershipMode = enabled ? .exclusive : .released
        guard requestedMode != inputOwnershipMode else {
            if enabled, let id = selectedDeviceID, !selectedDeviceConnected {
                if !attach(id: id) {
                    inputOwnershipMode = .released
                }
            }
            return
        }

        if !enabled {
            inputOwnershipMode = .released
            safetyState.stop()
            releaseManagerForCodex()
            activeProfileName = HIDInputOwnershipMode.released.label
            return
        }

        // The released state intentionally has no live manager. Recreate it
        // only when the operator explicitly asks LoudPilot to reclaim input.
        if manager == nil {
            start()
        }
        guard let manager else {
            inputOwnershipMode = .released
            selectedDeviceError = "HID manager is not running"
            return
        }
        if managerOpen {
            IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
            managerOpen = false
        }
        setControllerOnlyMatching(on: manager)
        let openResult = IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeSeizeDevice))
        guard openResult == kIOReturnSuccess else {
            inputOwnershipMode = .released
            selectedDeviceConnected = false
            selectedDeviceError = String(format: "macOS denied exclusive HID ownership (0x%08x)", UInt32(bitPattern: openResult))
            IOHIDManagerSetDeviceMatching(manager, nil)
            let reopenResult = IOHIDManagerOpen(manager, IOOptionBits(kIOHIDOptionsTypeNone))
            managerOpen = reopenResult == kIOReturnSuccess
            return
        }
        managerOpen = true
        inputOwnershipMode = .exclusive
        if let id = selectedDeviceID {
            _ = attach(id: id)
        }
    }

    /// Completely relinquishes HID ownership. A closed-but-scheduled manager
    /// can still be observed by macOS as an active consumer, which prevents
    /// the Codex app from reconnecting reliably. The manager, callbacks,
    /// buffers, and device references therefore all go away together.
    private func releaseManagerForCodex() {
        for id in Array(deviceByID.keys) {
            clearDeviceState(id: id)
        }
        guard let manager else {
            clearActiveInputState()
            return
        }
        IOHIDManagerUnscheduleFromRunLoop(manager, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        if managerOpen {
            IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        }
        managerOpen = false
        self.manager = nil
        deviceByID.removeAll()
        devices.removeAll()
        selectedDeviceID = nil
        selectedDeviceConnected = false
        clearActiveInputState()
    }

    func selectDevice(id: String) {
        guard let summary = devices.first(where: { $0.id == id }), summary.isControllerCandidate else {
            selectedDeviceError = "Only a Codex Micro or Work Louder Micro can be used as the controller"
            return
        }
        if selectedDeviceID != id {
            if let old = selectedDeviceID {
                detach(id: old)
            }
            selectedDeviceID = id
            captureState = GuidedCaptureState(plan: .codexMicro)
            learnedMapping = nil
            if inputOwnershipMode.allowsLoudPilotInput, !attach(id: id) {
                inputOwnershipMode = .released
            }
        } else if inputOwnershipMode.allowsLoudPilotInput, !selectedDeviceConnected {
            if !attach(id: id) {
                inputOwnershipMode = .released
            }
        }
    }

    func retrySelectedDevice() {
        guard let id = selectedDeviceID else { return }
        guard inputOwnershipMode.allowsLoudPilotInput else { return }
        detach(id: id)
        if !attach(id: id) {
            inputOwnershipMode = .released
        }
    }

    /// Re-enumerates the current HID registry without changing ownership.
    ///
    /// A Bluetooth advertisement can become an HID service after the user
    /// connects it elsewhere. The metadata-only manager is intentionally kept
    /// open only for callbacks, so this explicit pass gives the UI a reliable
    /// retry action without seizing any device or reading control reports.
    func rescan() {
        guard let manager else {
            start()
            return
        }

        guard let devices = IOHIDManagerCopyDevices(manager) else {
            selectedDeviceError = "macOS returned no HID devices during rescan"
            return
        }

        for case let device as IOHIDDevice in devices as NSSet {
            handleMatched(device)
        }
    }

    func setFocused(_ focused: Bool) {
        safetyState.setFocused(focused)
    }

    func acceptCaptureStep() {
        guard captureState.acceptCurrentStep() else { return }
        learnedMapping = CodexMicroMappingPolicy.stagedMapping(
            from: captureState,
            interactionEvidence: interactionEvidence
        )
        refreshSelectedProfile()
    }

    func resetCaptureObservation() {
        captureState.resetCurrentObservation()
    }

    func resetCaptureSession() {
        captureState.reset()
        interactionEvidence.reset()
        learnedMapping = nil
        refreshSelectedProfile()
    }

    func triggerEmergencyStop() {
        emergencyStopTested = true
        safetyState.stop()
    }

    func clearEmergencyStop() {
        safetyState.clearStop()
    }

    func handleMatched(_ device: IOHIDDevice) {
        let summary = summarize(device)
        deviceByID[summary.id] = device
        if !devices.contains(where: { $0.id == summary.id }) {
            devices.append(summary)
            devices.sort { $0.product.localizedCaseInsensitiveCompare($1.product) == .orderedAscending }
        }
        if selectedDeviceID == nil && summary.isControllerCandidate {
            selectedDeviceID = summary.id
            captureState = GuidedCaptureState(plan: .codexMicro)
            learnedMapping = nil
            if inputOwnershipMode.allowsLoudPilotInput, !attach(id: summary.id) {
                inputOwnershipMode = .released
            }
        } else if selectedDeviceID == summary.id,
                  inputOwnershipMode.allowsLoudPilotInput,
                  !selectedDeviceConnected {
            _ = attach(id: summary.id)
        }
    }

    func handleRemoved(_ device: IOHIDDevice) {
        let summary = summarize(device)
        detach(id: summary.id)
        deviceByID.removeValue(forKey: summary.id)
        devices.removeAll { $0.id == summary.id }
        if selectedDeviceID == summary.id {
            selectedDeviceID = nil
            selectedDeviceConnected = false
            selectedDeviceError = nil
            activeProfileName = "None"
            safetyState.setConnected(false)
            captureState.reset()
            learnedMapping = nil
        }
    }

    @discardableResult
    private func attach(id: String) -> Bool {
        guard inputOwnershipMode.allowsLoudPilotInput else { return false }
        guard let device = deviceByID[id], managerOpen, bufferByID[id] == nil else {
            return bufferByID[id] != nil
        }
        let summary = summarize(device)
        let profile = learnedMapping?.profile ?? ControllerInputPolicy.profile(for: summary)
        activeProfileName = profile.name
        selectedDeviceError = nil
        let reportSize = max(64, Int(numberProperty(device, kIOHIDMaxInputReportSizeKey)))
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: reportSize)
        buffer.initialize(repeating: 0, count: reportSize)
        bufferByID[id] = buffer
        reportByID[id] = "—"
        interpreterByID[id] = HIDInputInterpreter()
        profileByID[id] = profile
        let context = Unmanaged.passUnretained(self).toOpaque()
        IOHIDDeviceRegisterInputReportCallback(
            device,
            buffer,
            reportSize,
            hidInputReport,
            context
        )
        IOHIDDeviceRegisterInputValueCallback(device, hidInputValue, context)
        IOHIDDeviceScheduleWithRunLoop(device, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        selectedDeviceConnected = true
        safetyState.setConnected(true)
        return true
    }

    private func detach(id: String) {
        clearDeviceState(id: id)
    }

    private func clearDeviceState(id: String) {
        if let device = deviceByID[id] {
            IOHIDDeviceUnscheduleFromRunLoop(device, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
            if let buffer = bufferByID.removeValue(forKey: id) {
                buffer.deinitialize(count: max(64, Int(numberProperty(device, kIOHIDMaxInputReportSizeKey))))
                buffer.deallocate()
            }
        }
        interpreterByID.removeValue(forKey: id)
        reportByID.removeValue(forKey: id)
        profileByID.removeValue(forKey: id)
        if selectedDeviceID == id {
            selectedDeviceConnected = false
            selectedDeviceError = nil
            activeProfileName = inputOwnershipMode.label
            clearActiveInputState()
        }
    }

    private func clearActiveInputState() {
        safetyState.setConnected(false)
        reportCount = 0
        lastReportHex = "—"
        lastReportAt = nil
        interactionEvidence.reset()
        events.removeAll()
    }

    private func setControllerOnlyMatching(on manager: IOHIDManager) {
        let knownDescriptor: [String: Any] = [
            kIOHIDVendorIDKey: NSNumber(value: ControllerDeviceScope.codexMicroVendorID),
            kIOHIDProductIDKey: NSNumber(value: ControllerDeviceScope.codexMicroProductID)
        ]
        let namedProducts = ControllerDeviceScope.exclusiveProductNames.map { product in
            [kIOHIDProductKey: product] as [String: Any]
        }

        // The dictionaries are ORed by IOHIDManager. This preserves the
        // narrow known VID/PID path while allowing a valid named Micro HID
        // device to be claimed when its transport descriptor differs.
        IOHIDManagerSetDeviceMatchingMultiple(
            manager,
            ([knownDescriptor] + namedProducts) as CFArray
        )
    }

    func handleReport(device: IOHIDDevice, report: UnsafeMutablePointer<UInt8>?, length: CFIndex) {
        guard inputOwnershipMode.allowsLoudPilotInput,
              selectedDeviceConnected,
              let report,
              let id = deviceID(device),
              length > 0 else { return }
        let data = Data(bytes: report, count: Int(length))
        let hex = data.map { String(format: "%02x", $0) }.joined(separator: " ")
        reportByID[id] = hex
        lastReportHex = hex
        reportCount += 1
        lastReportAt = Date().timeIntervalSince1970
    }

    func handleValue(device: IOHIDDevice, value: IOHIDValue) {
        guard inputOwnershipMode.allowsLoudPilotInput,
              selectedDeviceConnected,
              let id = deviceID(device),
              id == selectedDeviceID else { return }
        let element = IOHIDValueGetElement(value)
        let descriptor = HIDElementDescriptor(
            identifier: "\(id):\(IOHIDElementGetCookie(element))",
            usagePage: IOHIDElementGetUsagePage(element),
            usage: IOHIDElementGetUsage(element),
            isRelative: IOHIDElementIsRelative(element)
        )
        guard var interpreter = interpreterByID[id] else { return }
        let rawEvent = interpreter.ingest(
            descriptor: descriptor,
            value: Double(IOHIDValueGetIntegerValue(value)),
            timestamp: Date().timeIntervalSince1970
        )
        interpreterByID[id] = interpreter

        // Focus loss is a hard observation boundary. Still pass releases to
        // the safety state so a suppressed held input can be re-armed only
        // after an actual release; do not capture or map background events.
        guard safetyState.focused else {
            if rawEvent.phase == .released {
                safetyState.ingest(rawEvent)
            }
            return
        }

        interactionEvidence.observe(rawEvent)
        let profile = profileByID[id] ?? ControllerInputPolicy.profile(for: summarize(device))
        captureState.ingest(
            descriptor: descriptor,
            event: rawEvent,
            rawReport: reportByID[id] ?? "—"
        )
        guard HIDInputPolicy.shouldSurfaceAsPhysicalEvent(rawEvent) else {
            return
        }
        let event: MicroInputEvent
        switch profile.action(for: descriptor) {
        case .control(let control, let scale):
            event = MicroInputEvent(
                identifier: rawEvent.identifier,
                kind: rawEvent.kind,
                value: rawEvent.value,
                phase: rawEvent.phase,
                timestamp: rawEvent.timestamp,
                controlMapping: control,
                controlScale: scale
            )
            safetyState.ingest(event)
        case .relativeControl(let control, let scale):
            event = MicroInputEvent(
                identifier: rawEvent.identifier,
                kind: rawEvent.kind,
                value: rawEvent.value,
                phase: rawEvent.phase,
                timestamp: rawEvent.timestamp,
                controlMapping: control,
                controlScale: scale
            )
            safetyState.ingest(event)
        case .stop:
            emergencyStopTested = true
            safetyState.stop()
            event = rawEvent
        case nil:
            event = rawEvent
            safetyState.ingest(event)
        }
        let observed = ObservedHIDEvent(
            event: event,
            usagePage: descriptor.usagePage,
            usage: descriptor.usage,
            rawReport: reportByID[id] ?? "—"
        )
        events.insert(observed, at: 0)
        if events.count > 80 { events.removeLast(events.count - 80) }
    }

    private func refreshSelectedProfile() {
        guard let id = selectedDeviceID, let device = deviceByID[id] else { return }
        let summary = summarize(device)
        let profile = learnedMapping?.profile ?? ControllerInputPolicy.profile(for: summary)
        profileByID[id] = profile
        activeProfileName = selectedDeviceConnected ? profile.name : inputOwnershipMode.label
    }

    private func summarize(_ device: IOHIDDevice) -> HIDDeviceSummary {
        let vendor = numberProperty(device, kIOHIDVendorIDKey)
        let productID = numberProperty(device, kIOHIDProductIDKey)
        let location = numberProperty(device, kIOHIDLocationIDKey)
        let id = "\(vendor):\(productID):\(location)"
        return HIDDeviceSummary(
            id: id,
            product: stringProperty(device, kIOHIDProductKey),
            manufacturer: stringProperty(device, kIOHIDManufacturerKey),
            transport: stringProperty(device, kIOHIDTransportKey),
            vendorID: vendor,
            productID: productID
        )
    }

    private func deviceID(_ device: IOHIDDevice) -> String? {
        let id = summarize(device).id
        return deviceByID[id] != nil ? id : nil
    }

    private func stringProperty(_ device: IOHIDDevice, _ key: String) -> String {
        guard let value = IOHIDDeviceGetProperty(device, key as CFString) else { return "Unknown" }
        return String(describing: value)
    }

    private func numberProperty(_ device: IOHIDDevice, _ key: String) -> UInt64 {
        guard let value = IOHIDDeviceGetProperty(device, key as CFString) else { return 0 }
        if let number = value as? NSNumber { return number.uint64Value }
        return UInt64(String(describing: value)) ?? 0
    }
}

private let hidDeviceMatched: IOHIDDeviceCallback = { context, _, _, device in
    guard let context else { return }
    let monitor = Unmanaged<HIDMonitor>.fromOpaque(context).takeUnretainedValue()
    DispatchQueue.main.async { monitor.handleMatched(device) }
}

private let hidDeviceRemoved: IOHIDDeviceCallback = { context, _, _, device in
    guard let context else { return }
    let monitor = Unmanaged<HIDMonitor>.fromOpaque(context).takeUnretainedValue()
    DispatchQueue.main.async { monitor.handleRemoved(device) }
}

private let hidInputReport: IOHIDReportCallback = { context, _, sender, _, _, report, length in
    guard let context, let sender else { return }
    let monitor = Unmanaged<HIDMonitor>.fromOpaque(context).takeUnretainedValue()
    let device = unsafeBitCast(sender, to: IOHIDDevice.self)
    DispatchQueue.main.async { monitor.handleReport(device: device, report: report, length: length) }
}

private let hidInputValue: IOHIDValueCallback = { context, _, sender, value in
    guard let context, let sender else { return }
    let monitor = Unmanaged<HIDMonitor>.fromOpaque(context).takeUnretainedValue()
    let device = unsafeBitCast(sender, to: IOHIDDevice.self)
    DispatchQueue.main.async { monitor.handleValue(device: device, value: value) }
}
