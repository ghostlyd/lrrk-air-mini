// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "LiteWingMicroController",
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
            name: "LiteWingMicroControllerCore",
            path: "Sources/LiteWingMicroControllerCore"
        ),
        .executableTarget(
            name: "LoudPilot",
            dependencies: ["LiteWingMicroControllerCore"],
            path: "Sources/LiteWingMicroController"
        ),
        .executableTarget(
            name: "LiteWingMicroControllerTests",
            dependencies: ["LiteWingMicroControllerCore"],
            path: "Tests/LiteWingMicroControllerTests"
        ),
    ]
)
