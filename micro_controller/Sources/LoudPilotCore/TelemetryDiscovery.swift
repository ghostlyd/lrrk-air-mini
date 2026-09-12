import Foundation

/// Selects only variables that the live log TOC positively advertises.
///
/// The positioning shield is intentionally not part of this allow-list. A
/// missing or unverified sensor therefore never appears as a numeric zero.
public enum TelemetryDiscoveryPlan {
    private static let primaryPaths = [
        "pm.vbat",
        "gyro.x",
        "gyro.y",
        "gyro.z",
    ]
    private static let accelerometerPaths = [
        "acc.x",
        "acc.y",
        "acc.z",
    ]

    public static func schemas(from variables: [LogVariable]) -> [LogBlockSchema] {
        let byPath = Dictionary(uniqueKeysWithValues: variables.map { ($0.path, $0) })
        var schemas: [LogBlockSchema] = []

        let primary = primaryPaths.compactMap { path -> LogVariable? in
            guard let variable = byPath[path], variable.type != .float16 else { return nil }
            return variable
        }
        if !primary.isEmpty {
            schemas.append(LogBlockSchema(blockID: 1, variables: primary))
        }

        let accelerometer = accelerometerPaths.compactMap { path -> LogVariable? in
            guard let variable = byPath[path], variable.type != .float16 else { return nil }
            return variable
        }
        if !accelerometer.isEmpty {
            schemas.append(LogBlockSchema(blockID: 2, variables: accelerometer))
        }

        return schemas
    }
}
