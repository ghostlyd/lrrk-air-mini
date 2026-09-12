import Combine
import Foundation
import IOKit.hid
import LiteWingMicroControllerCore

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
    @Published private(set) var reportCount = 0
    @Published private(set) var lastReportHex = "—"
    @Published private(set) var events: [ObservedHIDEvent] = []
    @Published private(set) var safetyState = InputSafetyState(bindings: [:])
    @Published private(set) var captureState = GuidedCaptureState(plan: .codexMicro)

    private var manager: IOHIDManager?
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
        let result = IOHIDManagerOpen(created, IOOptionBits(kIOHIDOptionsTypeNone))
        guard result == kIOReturnSuccess else {
            manager = nil
            return
        }
    }

    func stop() {
        guard let manager else { return }
        for id in Array(deviceByID.keys) {
            detach(id: id)
        }
        IOHIDManagerUnscheduleFromRunLoop(manager, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        IOHIDManagerClose(manager, IOOptionBits(kIOHIDOptionsTypeNone))
        self.manager = nil
        safetyState.setConnected(false)
        selectedDeviceConnected = false
        captureState.reset()
    }

    func selectDevice(id: String) {
        if selectedDeviceID != id {
            if let old = selectedDeviceID {
                detach(id: old)
            }
            selectedDeviceID = id
            attach(id: id)
        }
    }

    func retrySelectedDevice() {
        guard let id = selectedDeviceID else { return }
        detach(id: id)
        attach(id: id)
    }

    func setFocused(_ focused: Bool) {
        safetyState.setFocused(focused)
    }

    func acceptCaptureStep() {
        _ = captureState.acceptCurrentStep()
    }

    func resetCaptureObservation() {
        captureState.resetCurrentObservation()
    }

    func resetCaptureSession() {
        captureState.reset()
    }

    func handleMatched(_ device: IOHIDDevice) {
        let summary = summarize(device)
        deviceByID[summary.id] = device
        if !devices.contains(where: { $0.id == summary.id }) {
            devices.append(summary)
            devices.sort { $0.product.localizedCaseInsensitiveCompare($1.product) == .orderedAscending }
        }
        if selectedDeviceID == nil && summary.isMicroCandidate {
            selectedDeviceID = summary.id
            attach(id: summary.id)
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
        }
    }

    private func attach(id: String) {
        guard let device = deviceByID[id], bufferByID[id] == nil else { return }
        activeProfileName = profile(for: device).name
        captureState = GuidedCaptureState(plan: capturePlan(for: device))
        let openResult = IOHIDDeviceOpen(device, IOOptionBits(kIOHIDOptionsTypeNone))
        guard openResult == kIOReturnSuccess else {
            selectedDeviceConnected = false
            selectedDeviceError = String(format: "IOHIDDeviceOpen failed (0x%08x)", UInt32(bitPattern: openResult))
            safetyState.setConnected(false)
            return
        }
        selectedDeviceError = nil
        let reportSize = max(64, Int(numberProperty(device, kIOHIDMaxInputReportSizeKey)))
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: reportSize)
        buffer.initialize(repeating: 0, count: reportSize)
        bufferByID[id] = buffer
        reportByID[id] = "—"
        interpreterByID[id] = HIDInputInterpreter()
        profileByID[id] = profile(for: device)
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
    }

    private func detach(id: String) {
        guard let device = deviceByID[id] else { return }
        IOHIDDeviceUnscheduleFromRunLoop(device, CFRunLoopGetMain(), CFRunLoopMode.defaultMode.rawValue)
        IOHIDDeviceClose(device, IOOptionBits(kIOHIDOptionsTypeNone))
        if let buffer = bufferByID.removeValue(forKey: id) {
            buffer.deinitialize(count: max(64, Int(numberProperty(device, kIOHIDMaxInputReportSizeKey))))
            buffer.deallocate()
        }
        interpreterByID.removeValue(forKey: id)
        reportByID.removeValue(forKey: id)
        profileByID.removeValue(forKey: id)
        if selectedDeviceID == id {
            selectedDeviceConnected = false
            selectedDeviceError = nil
            activeProfileName = "None"
            safetyState.setConnected(false)
            captureState.reset()
        }
    }

    func handleReport(device: IOHIDDevice, report: UnsafeMutablePointer<UInt8>?, length: CFIndex) {
        guard let report, let id = deviceID(device), length > 0 else { return }
        let data = Data(bytes: report, count: Int(length))
        let hex = data.map { String(format: "%02x", $0) }.joined(separator: " ")
        reportByID[id] = hex
        lastReportHex = hex
        reportCount += 1
    }

    func handleValue(device: IOHIDDevice, value: IOHIDValue) {
        guard let id = deviceID(device), id == selectedDeviceID else { return }
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
        let profile = profileByID[id] ?? profile(for: device)
        captureState.ingest(
            descriptor: descriptor,
            event: rawEvent,
            rawReport: reportByID[id] ?? "—"
        )
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
        case .stop:
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

    private func profile(for device: IOHIDDevice) -> HIDControlProfile {
        let summary = summarize(device)
        let product = summary.product.lowercased()
        if product.contains("magic keyboard") {
            return BuiltInControlProfiles.magicKeyboard
        }
        if product.contains("codex micro") || product.contains("work louder") {
            return BuiltInControlProfiles.codexMicro
        }
        return BuiltInControlProfiles.unmapped
    }

    private func capturePlan(for device: IOHIDDevice) -> GuidedCapturePlan {
        let product = summarize(device).product.lowercased()
        if product.contains("magic keyboard") {
            return .magicKeyboard
        }
        return .codexMicro
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
