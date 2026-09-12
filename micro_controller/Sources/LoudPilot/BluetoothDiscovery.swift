import Combine
import Foundation
import LoudPilotCore
import os
@preconcurrency import CoreBluetooth

/// In-app BLE discovery for the physical controller. Discovery is deliberately
/// separate from HID input: a BLE advertisement is evidence that a device is
/// nearby, not permission to use it as a pilot input source.
@MainActor
final class BluetoothDiscovery: NSObject, ObservableObject {
    @Published private(set) var status: BluetoothDiscoveryStatus = .unavailable
    @Published private(set) var peripherals: [BluetoothPeripheralSummary] = []
    @Published private(set) var isScanning = false

    private var central: CBCentralManager?
    private var stopTask: Task<Void, Never>?
    private var scanRequested = false
    private let logger = Logger(subsystem: "ai.lrrk.loudpilot", category: "BluetoothDiscovery")

    override init() {
        super.init()
    }

    func start() {
        guard central == nil else { return }
        central = CBCentralManager(
            delegate: self,
            queue: nil,
            options: [CBCentralManagerOptionShowPowerAlertKey: true]
        )
        logger.info("initialized central state=\(String(describing: self.central?.state.rawValue), privacy: .public) authorization=\(CBManager.authorization.rawValue, privacy: .public)")
        if let central {
            update(central.state)
        }
    }

    deinit {
        stopTask?.cancel()
    }

    var controllerCandidates: [BluetoothPeripheralSummary] {
        BluetoothDiscoveryPolicy.controllerCandidates(from: peripherals)
    }

    func discover() {
        start()
        logger.info("discover requested state=\(String(describing: self.central?.state.rawValue), privacy: .public) scanning=\(self.isScanning, privacy: .public)")
        stopTask?.cancel()
        stopTask = nil
        peripherals.removeAll()
        scanRequested = true

        guard let central else {
            status = .initializing
            return
        }
        // The first CoreBluetooth state callback can race the initial button
        // press. Reconcile the current state here and let
        // `centralManagerDidUpdateState` finish the scan when the manager is
        // still resolving from `.unknown`.
        update(central.state)
        guard central.state == .poweredOn else {
            return
        }

        beginScan(on: central)
    }

    func stop() {
        logger.info("stop requested state=\(String(describing: self.central?.state.rawValue), privacy: .public) scanning=\(self.isScanning, privacy: .public)")
        stopTask?.cancel()
        stopTask = nil
        scanRequested = false
        central?.stopScan()
        isScanning = false
        if status == .scanning {
            status = .poweredOn
        }
    }

    private func beginScan(on central: CBCentralManager) {
        guard central.state == .poweredOn, !isScanning else { return }
        logger.info("begin scan state=\(central.state.rawValue, privacy: .public)")
        isScanning = true
        status = .scanning
        central.scanForPeripherals(
            withServices: nil,
            options: [CBCentralManagerScanOptionAllowDuplicatesKey: false]
        )
        stopTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(8))
            guard !Task.isCancelled else { return }
            self?.stop()
        }
    }

    private func record(_ peripheral: BluetoothPeripheralSummary) {
        if let index = peripherals.firstIndex(where: { $0.id == peripheral.id }) {
            peripherals[index] = peripheral
        } else {
            peripherals.append(peripheral)
        }
        peripherals.sort { lhs, rhs in
            if lhs.isControllerCandidate != rhs.isControllerCandidate {
                return lhs.isControllerCandidate
            }
            if lhs.rssi != rhs.rssi { return lhs.rssi > rhs.rssi }
            return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
        }
    }

    private func update(_ centralState: CBManagerState) {
        let next = Self.status(for: centralState)
        status = isScanning && next == .poweredOn ? .scanning : next
        if next != .poweredOn && isScanning {
            stopTask?.cancel()
            stopTask = nil
            central?.stopScan()
            isScanning = false
        }
        if next == .poweredOn, scanRequested, let central {
            beginScan(on: central)
        }
    }

    private static func status(for state: CBManagerState) -> BluetoothDiscoveryStatus {
        switch state {
        // CoreBluetooth can report `.unknown` while macOS is resolving the
        // app's Bluetooth authorization or bringing the manager online. It
        // is not evidence that Bluetooth is unavailable, and it is not a
        // usable controller connection either.
        case .unknown: return .initializing
        case .resetting: return .resetting
        case .unsupported: return .unsupported
        case .unauthorized: return .unauthorized
        case .poweredOff: return .poweredOff
        case .poweredOn: return .poweredOn
        @unknown default: return .initializing
        }
    }
}

extension BluetoothDiscovery: CBCentralManagerDelegate {
    nonisolated func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let nextState = central.state
        Logger(subsystem: "ai.lrrk.loudpilot", category: "BluetoothDiscovery")
            .info("central state callback=\(nextState.rawValue, privacy: .public)")
        Task { @MainActor [weak self] in
            self?.update(nextState)
        }
    }

    nonisolated func centralManager(
        _ central: CBCentralManager,
        didDiscover peripheral: CBPeripheral,
        advertisementData: [String: Any],
        rssi RSSI: NSNumber
    ) {
        let advertisedName = advertisementData[CBAdvertisementDataLocalNameKey] as? String
        let name = advertisedName ?? peripheral.name ?? "Unnamed Bluetooth peripheral"
        let summary = BluetoothPeripheralSummary(
            id: peripheral.identifier.uuidString,
            name: name,
            rssi: RSSI.intValue
        )
        Task { @MainActor [weak self] in
            self?.record(summary)
        }
    }
}
