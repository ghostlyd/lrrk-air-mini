// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "LoudPilot",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(
            name: "LoudPilot",
            targets: ["LoudPilot"]
        ),
    ],
    targets: [
        .target(
            name: "LoudPilotCore",
            path: "Sources/LoudPilotCore"
        ),
        .executableTarget(
            name: "LoudPilot",
            dependencies: ["LoudPilotCore"],
            path: "Sources/LoudPilot"
        ),
        .executableTarget(
            name: "LoudPilotTests",
            dependencies: ["LoudPilotCore"],
            path: "Tests/LoudPilotTests"
        ),
    ]
)
