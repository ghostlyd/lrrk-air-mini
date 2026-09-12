import Combine
import Foundation
import LoudPilotCore
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

    override init() {
        super.init()
        central = CBCentralManager(
            delegate: self,
            queue: nil,
            options: [CBCentralManagerOptionShowPowerAlertKey: true]
        )
    }

    deinit {
        stopTask?.cancel()
    }

    var controllerCandidates: [BluetoothPeripheralSummary] {
        BluetoothDiscoveryPolicy.controllerCandidates(from: peripherals)
    }

    func discover() {
        stopTask?.cancel()
        stopTask = nil
        peripherals.removeAll()

        guard let central else {
            status = .unavailable
            return
        }
        guard central.state == .poweredOn else {
            status = Self.status(for: central.state)
            return
        }

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

    func stop() {
        stopTask?.cancel()
        stopTask = nil
        central?.stopScan()
        isScanning = false
        if status == .scanning {
            status = .poweredOn
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
            central?.stopScan()
            isScanning = false
        }
    }

    private static func status(for state: CBManagerState) -> BluetoothDiscoveryStatus {
        switch state {
        case .unknown: return .unavailable
        case .resetting: return .resetting
        case .unsupported: return .unsupported
        case .unauthorized: return .unauthorized
        case .poweredOff: return .poweredOff
        case .poweredOn: return .poweredOn
        @unknown default: return .unavailable
        }
    }
}

extension BluetoothDiscovery: CBCentralManagerDelegate {
    nonisolated func centralManagerDidUpdateState(_ central: CBCentralManager) {
        let nextState = central.state
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
