import Foundation

/// Drives the Documents list screen (list, create, and a peek at Files).
@MainActor
final class DocumentsViewModel: ObservableObject {
    @Published private(set) var documents: [Document] = []
    @Published private(set) var files: [FileItem] = []
    @Published var isLoading = false
    @Published var isCreating = false
    @Published var errorMessage: String?

    private let api: OtterWorksAPIClient

    init(api: OtterWorksAPIClient) {
        self.api = api
    }

    func refresh() async {
        errorMessage = nil
        isLoading = true
        defer { isLoading = false }
        do {
            async let docs = api.documents()
            async let fileList = api.files()
            documents = try await docs.items
            files = try await fileList.files
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Creates a document. Returns `true` on success so the caller can clear
    /// its input only when the title was actually accepted.
    @discardableResult
    func create(title: String) async -> Bool {
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return false }

        errorMessage = nil
        isCreating = true
        defer { isCreating = false }
        do {
            let created = try await api.createDocument(title: trimmed)
            documents.insert(created, at: 0)
            return true
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }
        return false
    }
}
