import Combine
import Foundation
import LoudPilotCore
import Network

enum TelemetryConnectionStatus: Equatable {
    case disconnected
    case connecting
    case discoveringTOC
    case subscribing
    case streaming
    case stale
    case failed(String)

    var label: String {
        switch self {
        case .disconnected: return "Disconnected"
        case .connecting: return "Connecting"
        case .discoveringTOC: return "Discovering log variables"
        case .subscribing: return "Subscribing to telemetry"
        case .streaming: return "Streaming telemetry"
        case .stale: return "Telemetry stale"
        case .failed(let message): return "Failed: \(message)"
        }
    }
}

struct TelemetryEndpoint: Equatable {
    var host: String
    var port: UInt16

    init(host: String = "192.168.43.42", port: UInt16 = 2390) {
        self.host = host
        self.port = port
    }
}

@MainActor
final class TelemetryClient: ObservableObject {
    @Published private(set) var status: TelemetryConnectionStatus = .disconnected
    @Published private(set) var telemetryFreshness: TelemetryFreshness = .unavailable
    @Published private(set) var state = DroneTelemetryState()
    @Published private(set) var discoveredVariables: [LogVariable] = []
    @Published private(set) var activeSchemas: [LogBlockSchema] = []
    @Published private(set) var lastPacketAt: TimeInterval?
    @Published private(set) var inboundPacketCount = 0
    @Published private(set) var outboundTelemetryPacketCount = 0
    @Published private(set) var lastInboundHex = "—"
    @Published private(set) var lastOutboundHex = "—"

    var endpoint = TelemetryEndpoint()

    private var connection: NWConnection?
    private var tocCount: UInt16?
    private var nextTOCID: UInt16 = 0
    private var variablesByID: [UInt16: LogVariable] = [:]
    private var staleTask: Task<Void, Never>?
    private var discoveryTask: Task<Void, Never>?

    func connect(to endpoint: TelemetryEndpoint) {
        disconnect()
        self.endpoint = endpoint
        guard let port = NWEndpoint.Port(rawValue: endpoint.port), !endpoint.host.isEmpty else {
            status = .failed("invalid endpoint")
            return
        }

        status = .connecting
        telemetryFreshness = .unavailable
        let connection = NWConnection(
            host: NWEndpoint.Host(endpoint.host),
            port: port,
            using: .udp
        )
        self.connection = connection
        connection.stateUpdateHandler = { [weak self] state in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.handleConnectionState(state)
            }
        }
        connection.start(queue: .main)
        receiveNext()
        discoveryTask = Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(5))
            guard let self, !Task.isCancelled, self.connection != nil, self.inboundPacketCount == 0 else { return }
            self.status = .failed("no telemetry response from \(self.endpoint.host):\(self.endpoint.port)")
        }
        staleTask = Task { @MainActor [weak self] in
            while let self, !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard !Task.isCancelled else { return }
                self.updateStaleStatus()
            }
        }
    }

    func disconnect() {
        discoveryTask?.cancel()
        discoveryTask = nil
        staleTask?.cancel()
        staleTask = nil
        connection?.cancel()
        connection = nil
        status = .disconnected
        telemetryFreshness = .unavailable
        tocCount = nil
        nextTOCID = 0
        variablesByID.removeAll()
        discoveredVariables = []
        activeSchemas = []
        state = DroneTelemetryState()
        lastPacketAt = nil
        inboundPacketCount = 0
        outboundTelemetryPacketCount = 0
        lastInboundHex = "—"
        lastOutboundHex = "—"
    }

    private func handleConnectionState(_ newState: NWConnection.State) {
        switch newState {
        case .ready:
            status = .discoveringTOC
            sendTelemetry(try? LiteWingTelemetryWire.logTOCInfoRequest())
        case .failed(let error):
            status = .failed(error.localizedDescription)
            telemetryFreshness = .unavailable
        case .cancelled:
            if status != .disconnected {
                status = .disconnected
            }
            telemetryFreshness = .unavailable
        case .waiting(let error):
            status = .failed(error.localizedDescription)
            telemetryFreshness = .unavailable
        case .preparing, .setup:
            break
        @unknown default:
            break
        }
    }

    private func receiveNext() {
        guard let connection else { return }
        connection.receiveMessage { [weak self] data, _, _, error in
            Task { @MainActor [weak self] in
                guard let self else { return }
                if let error {
                    self.status = .failed(error.localizedDescription)
                    self.telemetryFreshness = .unavailable
                }
                if let data, !data.isEmpty {
                    self.handleInbound(data)
                }
                if self.connection != nil {
                    self.receiveNext()
                }
            }
        }
    }

    private func sendTelemetry(_ packet: [UInt8]?) {
        guard let packet, let connection else { return }
        lastOutboundHex = packet.hex
        outboundTelemetryPacketCount += 1
        connection.send(content: Data(packet), completion: .contentProcessed { [weak self] error in
            guard let error else { return }
            Task { @MainActor [weak self] in
                self?.status = .failed(error.localizedDescription)
                self?.telemetryFreshness = .unavailable
            }
        })
    }

    private func handleInbound(_ data: Data) {
        let packet = Array(data)
        lastInboundHex = packet.hex
        inboundPacketCount += 1
        let now = Date().timeIntervalSince1970
        do {
            let decoded = try LiteWingTelemetryWire.decode(packet)
            lastPacketAt = now
            switch decoded.header & 0x0F {
            case 0:
                handleTOCResponse(decoded.payload)
            case 1:
                handleControlResponse(decoded.payload)
            case 2:
                handleLogData(decoded.payload, receivedAt: now)
            default:
                break
            }
        } catch {
            status = .failed(error.localizedDescription)
            telemetryFreshness = .unavailable
        }
    }

    private func handleTOCResponse(_ payload: [UInt8]) {
        guard let opcode = payload.first else { return }
        switch opcode {
        case 3 where payload.count >= 3:
            tocCount = UInt16(payload[1]) | UInt16(payload[2]) << 8
            nextTOCID = 0
            variablesByID.removeAll()
            requestNextTOCItem()
        case 2:
            guard let item = try? LiteWingTelemetryWire.decodeTOCItem(payload) else { return }
            variablesByID[item.id] = item
            nextTOCID &+= 1
            requestNextTOCItem()
        default:
            break
        }
    }

    private func requestNextTOCItem() {
        guard let tocCount else { return }
        guard nextTOCID < tocCount else {
            discoveredVariables = variablesByID.values.sorted { $0.id < $1.id }
            activeSchemas = TelemetryDiscoveryPlan.schemas(from: discoveredVariables)
            status = activeSchemas.isEmpty ? .failed("board advertised no supported battery/IMU log variables") : .subscribing
            subscribeToSchemas()
            return
        }
        sendTelemetry(try? LiteWingTelemetryWire.logTOCItemRequest(id: nextTOCID))
    }

    private func subscribeToSchemas() {
        guard !activeSchemas.isEmpty else { return }
        for schema in activeSchemas {
            sendTelemetry(try? LiteWingTelemetryWire.logCreateBlockRequest(
                blockID: schema.blockID,
                variables: schema.variables
            ))
            sendTelemetry(try? LiteWingTelemetryWire.logStartBlockRequest(
                blockID: schema.blockID,
                periodMilliseconds: 100
            ))
        }
    }

    private func handleControlResponse(_ payload: [UInt8]) {
        guard payload.count >= 2 else { return }
        // The manufacturer log-control ACK is subscription evidence only; it
        // is never treated as an arm or flight-control acknowledgement.
        if payload[0] == 6 || payload[0] == 3 {
            status = .streaming
        }
    }

    private func handleLogData(_ payload: [UInt8], receivedAt: TimeInterval) {
        guard let blockID = payload.first,
              let schema = activeSchemas.first(where: { $0.blockID == blockID }) else { return }
        do {
            try state.applyLogData(payload, schema: schema, receivedAt: receivedAt)
            if state.hasCompleteReadOnlyTelemetry {
                status = .streaming
                telemetryFreshness = .fresh
            } else {
                status = .subscribing
                telemetryFreshness = .unavailable
            }
        } catch {
            status = .failed(error.localizedDescription)
            telemetryFreshness = .unavailable
        }
    }

    private func updateStaleStatus() {
        guard case .streaming = status else { return }
        guard let age = state.completeTelemetryAge(now: Date().timeIntervalSince1970) else {
            status = .subscribing
            telemetryFreshness = .unavailable
            return
        }
        if age > 2.0 {
            status = .stale
            telemetryFreshness = .stale
        }
    }
}

private extension Array where Element == UInt8 {
    var hex: String {
        map { String(format: "%02x", $0) }.joined(separator: " ")
    }
}
