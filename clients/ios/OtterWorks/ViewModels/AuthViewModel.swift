import Foundation

/// Drives the Login and Register screens.
@MainActor
final class AuthViewModel: ObservableObject {
    @Published var isBusy = false
    @Published var errorMessage: String?

    private let api: OtterWorksAPIClient
    private let session: SessionStore

    init(api: OtterWorksAPIClient, session: SessionStore) {
        self.api = api
        self.session = session
    }

    func login(email: String, password: String) async {
        await run {
            let response = try await self.api.login(
                email: email.trimmingCharacters(in: .whitespacesAndNewlines),
                password: password)
            self.session.start(with: response)
        }
    }

    func register(displayName: String, email: String, password: String) async {
        await run {
            let response = try await self.api.register(
                displayName: displayName.trimmingCharacters(in: .whitespacesAndNewlines),
                email: email.trimmingCharacters(in: .whitespacesAndNewlines),
                password: password)
            self.session.start(with: response)
        }
    }

    private func run(_ operation: @escaping () async throws -> Void) async {
        errorMessage = nil
        isBusy = true
        defer { isBusy = false }
        do {
            try await operation()
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
