import SwiftUI

struct DocumentsView: View {
    @ObservedObject private var session: SessionStore
    @StateObject private var viewModel: DocumentsViewModel
    @State private var newTitle = ""

    init(api: OtterWorksAPIClient, session: SessionStore) {
        self.session = session
        _viewModel = StateObject(wrappedValue: DocumentsViewModel(api: api))
    }

    var body: some View {
        NavigationStack {
            List {
                if let error = viewModel.errorMessage {
                    Section {
                        Text(error).foregroundStyle(.red).font(.callout)
                    }
                }

                Section("New document") {
                    HStack {
                        TextField("Title", text: $newTitle)
                            .onSubmit(create)
                        Button("New", action: create)
                            .disabled(!canCreate)
                    }
                }

                Section("Documents") {
                    if viewModel.documents.isEmpty {
                        ContentUnavailableView(
                            "No documents yet",
                            systemImage: "doc.text",
                            description: Text("Create your first document above."))
                    } else {
                        ForEach(viewModel.documents) { document in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(document.title).font(.body)
                                if let updated = document.updatedAt {
                                    Text(updated, style: .date)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }

                if !viewModel.files.isEmpty {
                    Section("Files") {
                        ForEach(viewModel.files) { file in
                            VStack(alignment: .leading, spacing: 2) {
                                Text(file.name).font(.body)
                                if let detail = file.detailLine {
                                    Text(detail)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Documents")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    if let name = session.currentUser?.displayName {
                        Text(name).font(.subheadline).foregroundStyle(.secondary)
                    }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Log out", role: .destructive) { session.clear() }
                }
            }
            .overlay {
                if viewModel.isLoading && viewModel.documents.isEmpty {
                    ProgressView()
                }
            }
            .refreshable { await viewModel.refresh() }
            .task { await viewModel.refresh() }
        }
    }

    private var canCreate: Bool {
        !viewModel.isCreating && !newTitle.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func create() {
        guard canCreate else { return }
        let title = newTitle
        newTitle = ""
        Task { await viewModel.create(title: title) }
    }
}
