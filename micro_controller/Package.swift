// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "LiteWingMicroController",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .executable(
            name: "LiteWingMicroController",
            targets: ["LiteWingMicroController"]
        ),
    ],
    targets: [
        .target(
            name: "LiteWingMicroControllerCore",
            path: "Sources/LiteWingMicroControllerCore"
        ),
        .executableTarget(
            name: "LiteWingMicroController",
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
