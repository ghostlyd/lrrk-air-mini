import Foundation

/// Selects the command-path surface shown by LoudPilot.
///
/// `.emulatorPreview` renders the same LiteWing command encoding locally but
/// never opens a socket, USB endpoint, or motor-output path. The physical
/// mode remains a staged label until the independent output gate is satisfied.
public enum FlightOutputMode: String, CaseIterable, Codable, Sendable {
    case readOnly
    case emulatorPreview
    case liteWingStaged

    public var label: String {
        switch self {
        case .readOnly: return "Read-only"
        case .emulatorPreview: return "Emulator preview"
        case .liteWingStaged: return "LiteWing transport (staged)"
        }
    }

    public var detail: String {
        switch self {
        case .readOnly:
            return "Intended values and telemetry only; no command frame is produced."
        case .emulatorPreview:
            return "Local command frames are rendered for mapping tests. Nothing is transmitted."
        case .liteWingStaged:
            return "Physical command transport is present in the design but remains disconnected in this stage."
        }
    }

    public var isLocalOnly: Bool {
        self != .liteWingStaged
    }
}
