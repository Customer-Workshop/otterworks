import Foundation

// File payloads are snake_case (file-service contract).

/// A file as returned by the file service.
struct FileItem: Decodable, Identifiable {
    let id: String
    let name: String
    let sizeBytes: Int64?
    let mimeType: String?
    let createdAt: Date?

    /// A human-readable "size · type" line, omitting whichever fields are absent.
    var detailLine: String? {
        var parts: [String] = []
        if let sizeBytes {
            parts.append(ByteCountFormatter.string(fromByteCount: sizeBytes, countStyle: .file))
        }
        if let mimeType, !mimeType.isEmpty {
            parts.append(mimeType)
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

/// Paged response for `GET /files`.
struct FileListResponse: Decodable {
    let files: [FileItem]
    let total: Int?
    let page: Int?
    let pageSize: Int?
}
