import Foundation

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
        let haystack = "\(product) \(manufacturer)".lowercased()
        return haystack.contains("micro") || haystack.contains("codex")
    }
}
