import SwiftUI
import BackgroundTasks

@main
struct GaiaExporterApp: App {
    @StateObject private var appState = AppState()

    init() {
        // Register BG task and schedule the first refresh
        HealthKitBackgroundSync.shared.registerBGTask()
        HealthKitBackgroundSync.shared.registerProcessingTask()
        HealthKitBackgroundSync.shared.scheduleRefresh(after: 30) // minutes
        HealthKitBackgroundSync.shared.scheduleProcessing(after: 120)
        try? HealthKitBackgroundSync.shared.registerObservers()
        appLog("[BG] Registered background and processing tasks at launch")
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
        }
    }
}
