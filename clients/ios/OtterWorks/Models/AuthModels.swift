import Foundation

// Auth payloads are camelCase. These mirror the OtterWorks auth-service contract
// (see clients/windows-desktop for the sibling native client).

/// Request body for `POST /auth/register`.
struct RegisterRequest: Encodable {
    let displayName: String
    let email: String
    let password: String
}

/// Request body for `POST /auth/login`.
struct LoginRequest: Encodable {
    let email: String
    let password: String
}

/// Response body for `/auth/register` and `/auth/login`.
struct AuthResponse: Decodable {
    let accessToken: String
    let refreshToken: String?
    let tokenType: String?
    let expiresIn: Int?
    let user: AuthUser?
}

struct AuthUser: Decodable, Identifiable {
    let id: String
    let email: String
    let displayName: String?
}
