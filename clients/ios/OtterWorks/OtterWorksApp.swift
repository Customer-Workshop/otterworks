import SwiftUI

@main
struct OtterWorksApp: App {
    @StateObject private var session: SessionStore
    private let api: OtterWorksAPIClient
    private let settings: AppSettings

    init() {
        let settings = AppSettings.load()
        let session = SessionStore(persist: settings.persistTokens)
        // The client reads the current token lazily so it always sends the live value.
        let api = OtterWorksAPIClient(baseURL: settings.apiBaseURL) { [weak session] in
            await session?.accessToken
        }

        self.settings = settings
        self.api = api
        _session = StateObject(wrappedValue: session)
    }

    var body: some Scene {
        WindowGroup {
            RootView(api: api)
                .environmentObject(session)
        }
    }
}
