import SwiftUI

/// Top-level shell: shows the auth flow until a session exists, then the documents list.
struct RootView: View {
    @EnvironmentObject private var session: SessionStore
    private let api: OtterWorksAPIClient

    init(api: OtterWorksAPIClient) {
        self.api = api
    }

    var body: some View {
        Group {
            if session.isAuthenticated {
                DocumentsView(api: api, session: session)
            } else {
                LoginView(api: api, session: session)
            }
        }
        .animation(.default, value: session.isAuthenticated)
    }
}
