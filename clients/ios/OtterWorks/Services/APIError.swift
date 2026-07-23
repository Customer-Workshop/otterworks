import Foundation

/// A user-presentable error raised by `OtterWorksAPIClient`.
struct APIError: LocalizedError {
    let statusCode: Int
    let message: String

    var errorDescription: String? { message }

    /// Network-level failure (host unreachable, timeout, TLS, etc.).
    static func network(_ underlying: Error) -> APIError {
        APIError(
            statusCode: 0,
            message: "Could not reach the OtterWorks backend. Verify it is running and that the "
                + "API base URL is correct.\n\n\(underlying.localizedDescription)")
    }

    static func decoding() -> APIError {
        APIError(statusCode: 0, message: "The OtterWorks backend returned an unexpected response.")
    }

    /// Extract a human-readable message from a JSON error body, falling back to the raw body.
    static func from(statusCode: Int, body: Data) -> APIError {
        if let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
            for key in ["message", "error", "detail"] {
                if let value = object[key] as? String, !value.isEmpty {
                    return APIError(statusCode: statusCode, message: value)
                }
            }
        }
        if let text = String(data: body, encoding: .utf8),
           !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return APIError(statusCode: statusCode, message: text)
        }
        return APIError(statusCode: statusCode, message: "Request failed with status \(statusCode).")
    }
}
