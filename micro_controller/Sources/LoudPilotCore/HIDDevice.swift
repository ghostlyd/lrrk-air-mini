import Foundation

public enum HIDInputOwnershipMode: String, Equatable, Sendable {
    case released
    case exclusive

    public var allowsLoudPilotInput: Bool {
        self == .exclusive
    }

    public var label: String {
        switch self {
        case .released:
            return "Released to Codex app"
        case .exclusive:
            return "LoudPilot exclusive"
        }
    }
}

public struct HIDDeviceSummary: Identifiable, Equatable, Sendable {
    public let id: String
    public let product: String
    public let manufacturer: String
    public let transport: String
    public let vendorID: UInt64
    public let productID: UInt64

    public init(
        id: String,
        product: String,
        manufacturer: String,
        transport: String,
        vendorID: UInt64,
        productID: UInt64
    ) {
        self.id = id
        self.product = product
        self.manufacturer = manufacturer
        self.transport = transport
        self.vendorID = vendorID
        self.productID = productID
    }

    public var isMicroCandidate: Bool {
        isControllerCandidate
    }

    /// The only HID devices eligible to produce pilot input in LoudPilot.
    ///
    /// Other HID devices may still be enumerated for diagnostics, but they
    /// cannot be selected, mapped, or allowed into the control state.
    public var isControllerCandidate: Bool {
        ControllerDeviceScope.accepts(
            product: product,
            manufacturer: manufacturer,
            vendorID: vendorID,
            productID: productID
        )
    }
}

public enum ControllerDeviceScope {
    /// The USB identity observed for the Codex Micro Work Louder device.
    public static let codexMicroVendorID: UInt64 = 0x303A
    public static let codexMicroProductID: UInt64 = 0x8360

    public static func accepts(_ device: HIDDeviceSummary) -> Bool {
        accepts(
            product: device.product,
            manufacturer: device.manufacturer,
            vendorID: device.vendorID,
            productID: device.productID
        )
    }

    public static func accepts(
        product: String,
        manufacturer: String = "",
        vendorID: UInt64 = 0,
        productID: UInt64 = 0
    ) -> Bool {
        if vendorID == codexMicroVendorID && productID == codexMicroProductID {
            return true
        }

        let haystack = normalized("\(product) \(manufacturer)")
        return haystack.contains("codex micro") || haystack.contains("work louder micro")
    }

    public static func acceptsBluetoothName(_ name: String) -> Bool {
        let normalizedName = normalized(name)
        return normalizedName.contains("codex micro") || normalizedName.contains("work louder micro")
    }

    private static func normalized(_ value: String) -> String {
        value
            .lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .split(whereSeparator: { $0.isWhitespace || $0 == "_" || $0 == "-" })
            .joined(separator: " ")
    }
}

public struct BluetoothPeripheralSummary: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let rssi: Int
    public let isControllerCandidate: Bool

    public init(id: String, name: String, rssi: Int) {
        self.id = id
        self.name = name
        self.rssi = rssi
        self.isControllerCandidate = ControllerDeviceScope.acceptsBluetoothName(name)
    }

}

public enum BluetoothDiscoveryStatus: String, Equatable, Sendable {
    case unavailable
    case poweredOff
    case unauthorized
    case unsupported
    case resetting
    case poweredOn
    case scanning

    public var label: String {
        switch self {
        case .unavailable: return "Unavailable"
        case .poweredOff: return "Bluetooth off"
        case .unauthorized: return "Permission required"
        case .unsupported: return "Unsupported"
        case .resetting: return "Resetting"
        case .poweredOn: return "Ready"
        case .scanning: return "Scanning"
        }
    }
}

public enum BluetoothDiscoveryPolicy {
    public static func controllerCandidates(
        from peripherals: [BluetoothPeripheralSummary]
    ) -> [BluetoothPeripheralSummary] {
        peripherals
            .filter(\.isControllerCandidate)
            .sorted { lhs, rhs in
                if lhs.rssi != rhs.rssi { return lhs.rssi > rhs.rssi }
                return lhs.name.localizedCaseInsensitiveCompare(rhs.name) == .orderedAscending
            }
    }
}
