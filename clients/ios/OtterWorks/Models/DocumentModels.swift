import Foundation

// Document payloads are snake_case (document-service contract). A dedicated
// `JSONDecoder`/`JSONEncoder` with `.convertToSnakeCase` handles the mapping,
// so the Swift properties stay idiomatic camelCase.

/// Request body for `POST /documents`.
struct CreateDocumentRequest: Encodable {
    let title: String
}

/// A document as returned by the document service.
struct Document: Decodable, Identifiable {
    let id: String
    let title: String
    let content: String?
    let contentType: String?
    let ownerId: String?
    let folderId: String?
    let isDeleted: Bool?
    let wordCount: Int?
    let version: Int?
    let createdAt: Date?
    let updatedAt: Date?
}

/// Paged response for `GET /documents`.
struct DocumentListResponse: Decodable {
    let items: [Document]
    let total: Int?
    let page: Int?
    let size: Int?
    let pages: Int?
}
