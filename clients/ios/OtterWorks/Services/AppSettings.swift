import Foundation

/// Runtime configuration for the client.
///
/// The API base URL defaults to the local Docker Compose gateway and can be
/// overridden without recompiling by setting `OTTERWORKS_API_BASE_URL` in
/// `Info.plist` (mirrors `appsettings.json` in the Windows desktop client).
struct AppSettings {
    let apiBaseURL: URL
    let persistTokens: Bool

    static let defaultBaseURL = URL(string: "http://localhost:8080/api/v1")!

    static func load(bundle: Bundle = .main) -> AppSettings {
        let urlString = bundle.object(forInfoDictionaryKey: "OTTERWORKS_API_BASE_URL") as? String
        let base = urlString
            .flatMap { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .flatMap { $0.isEmpty ? nil : URL(string: $0) }
            ?? defaultBaseURL

        let persist = (bundle.object(forInfoDictionaryKey: "OTTERWORKS_PERSIST_TOKENS") as? Bool) ?? true

        return AppSettings(apiBaseURL: base, persistTokens: persist)
    }
}
