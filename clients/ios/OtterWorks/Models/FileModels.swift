import Foundation

// File payloads are snake_case (file-service contract).

/// A file as returned by the file service.
struct FileItem: Decodable, Identifiable {
    let id: String
    let name: String
    let size: Int64?
    let contentType: String?
    let createdAt: Date?
}

/// Paged response for `GET /files`.
struct FileListResponse: Decodable {
    let files: [FileItem]
    let total: Int?
    let page: Int?
    let pageSize: Int?
}
