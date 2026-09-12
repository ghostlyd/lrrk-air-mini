import SwiftUI

@main
struct LiteWingMicroControllerApp: App {
    var body: some Scene {
        WindowGroup("LiteWing Micro Controller") {
            DashboardView()
                .frame(minWidth: 860, minHeight: 720)
        }
        .windowResizability(.contentSize)
    }
}
