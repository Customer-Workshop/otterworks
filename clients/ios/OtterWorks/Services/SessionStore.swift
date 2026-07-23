import Foundation
import Security

/// Holds the authenticated session. The access token lives in memory and, when
/// `persistTokens` is enabled, is also stored in the iOS Keychain (never in
/// plaintext on disk) — the platform analogue of the Windows client's DPAPI store.
@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var accessToken: String?
    @Published private(set) var currentUser: AuthUser?

    private let persist: Bool
    private let keychainAccount = "com.otterworks.ios.accessToken"

    var isAuthenticated: Bool { accessToken != nil }

    init(persist: Bool) {
        self.persist = persist
        if persist {
            accessToken = Self.readToken(account: keychainAccount)
        }
    }

    func start(with response: AuthResponse) {
        accessToken = response.accessToken
        currentUser = response.user
        if persist {
            Self.writeToken(response.accessToken, account: keychainAccount)
        }
    }

    func clear() {
        accessToken = nil
        currentUser = nil
        if persist {
            Self.deleteToken(account: keychainAccount)
        }
    }

    // MARK: - Keychain helpers

    private static func baseQuery(account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: account,
        ]
    }

    private static func readToken(account: String) -> String? {
        var query = baseQuery(account: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    private static func writeToken(_ token: String, account: String) {
        deleteToken(account: account)
        var query = baseQuery(account: account)
        query[kSecValueData as String] = Data(token.utf8)
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(query as CFDictionary, nil)
    }

    private static func deleteToken(account: String) {
        SecItemDelete(baseQuery(account: account) as CFDictionary)
    }
}
