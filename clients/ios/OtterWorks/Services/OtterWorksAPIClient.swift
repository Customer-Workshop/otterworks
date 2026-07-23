import Foundation

/// Thin async REST client for the OtterWorks API gateway.
///
/// Auth payloads are camelCase and document/file payloads are snake_case, so the
/// client keeps two coder configurations and selects the right one per call.
actor OtterWorksAPIClient {
    private let baseURL: URL
    private let session: URLSession
    private let tokenProvider: @Sendable () async -> String?

    init(baseURL: URL, tokenProvider: @escaping @Sendable () async -> String?) {
        self.baseURL = baseURL
        self.tokenProvider = tokenProvider

        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        self.session = URLSession(configuration: config)
    }

    /// Whether payload keys are camelCase (auth) or snake_case (documents/files).
    private enum KeyStyle {
        case camelCase
        case snakeCase
    }

    // MARK: - Auth

    func register(displayName: String, email: String, password: String) async throws -> AuthResponse {
        let body = RegisterRequest(displayName: displayName, email: email, password: password)
        return try await send("auth/register", method: "POST", body: body, keys: .camelCase, authenticated: false)
    }

    func login(email: String, password: String) async throws -> AuthResponse {
        let body = LoginRequest(email: email, password: password)
        return try await send("auth/login", method: "POST", body: body, keys: .camelCase, authenticated: false)
    }

    // MARK: - Documents

    func documents(page: Int = 1, size: Int = 50) async throws -> DocumentListResponse {
        try await get("documents", query: ["page": "\(page)", "size": "\(size)"], keys: .snakeCase)
    }

    func createDocument(title: String) async throws -> Document {
        let body = CreateDocumentRequest(title: title)
        return try await send("documents", method: "POST", body: body, keys: .snakeCase)
    }

    // MARK: - Files

    func files(page: Int = 1, pageSize: Int = 50) async throws -> FileListResponse {
        try await get("files", query: ["page": "\(page)", "page_size": "\(pageSize)"], keys: .snakeCase)
    }

    // MARK: - Core request

    private func get<Response: Decodable>(
        _ path: String,
        query: [String: String] = [:],
        keys: KeyStyle,
        authenticated: Bool = true
    ) async throws -> Response {
        try await perform(path, method: "GET", bodyData: nil, query: query, keys: keys,
                          authenticated: authenticated)
    }

    private func send<Body: Encodable, Response: Decodable>(
        _ path: String,
        method: String,
        body: Body,
        query: [String: String] = [:],
        keys: KeyStyle,
        authenticated: Bool = true
    ) async throws -> Response {
        let data = try encoder(for: keys).encode(body)
        return try await perform(path, method: method, bodyData: data, query: query, keys: keys,
                                 authenticated: authenticated)
    }

    private func perform<Response: Decodable>(
        _ path: String,
        method: String,
        bodyData: Data?,
        query: [String: String],
        keys: KeyStyle,
        authenticated: Bool
    ) async throws -> Response {
        var request = URLRequest(url: buildURL(path: path, query: query))
        request.httpMethod = method

        if let bodyData {
            request.httpBody = bodyData
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if authenticated, let token = await tokenProvider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.network(error)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.decoding()
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.from(statusCode: http.statusCode, body: data)
        }

        do {
            return try decoder(for: keys).decode(Response.self, from: data)
        } catch {
            throw APIError.decoding()
        }
    }

    private func buildURL(path: String, query: [String: String]) -> URL {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        var components = URLComponents(
            url: baseURL.appendingPathComponent(trimmed),
            resolvingAgainstBaseURL: false)!
        if !query.isEmpty {
            components.queryItems = query
                .sorted { $0.key < $1.key }
                .map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        return components.url!
    }

    private func encoder(for keys: KeyStyle) -> JSONEncoder {
        let encoder = JSONEncoder()
        if keys == .snakeCase {
            encoder.keyEncodingStrategy = .convertToSnakeCase
        }
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }

    private func decoder(for keys: KeyStyle) -> JSONDecoder {
        let decoder = JSONDecoder()
        if keys == .snakeCase {
            decoder.keyDecodingStrategy = .convertFromSnakeCase
        }
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            if let date = OtterWorksAPIClient.iso8601WithFractional.date(from: raw)
                ?? OtterWorksAPIClient.iso8601Plain.date(from: raw) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: container, debugDescription: "Unrecognized date: \(raw)")
        }
        return decoder
    }

    private static let iso8601WithFractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    private static let iso8601Plain: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
}
