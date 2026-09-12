import Combine
import Foundation
@preconcurrency import Network

enum WiFiPathStatus: Equatable {
    case unavailable
    case connected

    var label: String {
        switch self {
        case .unavailable: return "Unavailable"
        case .connected: return "Ready"
        }
    }
}

/// Observes the Mac's Wi-Fi path only. It does not infer that the LiteWing
/// endpoint is reachable; fresh telemetry remains the authority for that.
@MainActor
final class WiFiPathMonitor: ObservableObject {
    @Published private(set) var status: WiFiPathStatus = .unavailable

    private let monitor = NWPathMonitor(requiredInterfaceType: .wifi)
    private let queue = DispatchQueue(label: "ai.lrrk.loudpilot.wifi-path")

    init() {
        monitor.pathUpdateHandler = { [weak self] path in
            let next: WiFiPathStatus = path.status == .satisfied ? .connected : .unavailable
            Task { @MainActor [weak self] in
                self?.status = next
            }
        }
        monitor.start(queue: queue)
    }

    deinit {
        monitor.cancel()
    }
}
