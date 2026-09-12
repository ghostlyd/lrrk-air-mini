import SwiftUI

@main
struct LoudPilotApp: App {
    var body: some Scene {
        WindowGroup("LoudPilot") {
            DashboardView()
                .frame(minWidth: 860, minHeight: 720)
        }
        .windowResizability(.contentSize)
    }
}
