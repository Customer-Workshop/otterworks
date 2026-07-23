import SwiftUI

struct LoginView: View {
    private let api: OtterWorksAPIClient
    private let session: SessionStore

    @StateObject private var viewModel: AuthViewModel
    @State private var email = ""
    @State private var password = ""
    @State private var showRegister = false

    init(api: OtterWorksAPIClient, session: SessionStore) {
        self.api = api
        self.session = session
        _viewModel = StateObject(wrappedValue: AuthViewModel(api: api, session: session))
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Email", text: $email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("Password", text: $password)
                        .textContentType(.password)
                }

                if let error = viewModel.errorMessage {
                    Section {
                        Text(error).foregroundStyle(.red).font(.callout)
                    }
                }

                Section {
                    Button(action: submit) {
                        HStack {
                            Spacer()
                            if viewModel.isBusy { ProgressView() } else { Text("Sign in") }
                            Spacer()
                        }
                    }
                    .disabled(!canSubmit)
                }

                Section {
                    Button("Need an account? Register") { showRegister = true }
                        .font(.callout)
                }
            }
            .navigationTitle("OtterWorks")
            .navigationDestination(isPresented: $showRegister) {
                RegisterView(api: api, session: session)
            }
        }
    }

    private var canSubmit: Bool {
        !viewModel.isBusy && !email.isEmpty && !password.isEmpty
    }

    private func submit() {
        Task { await viewModel.login(email: email, password: password) }
    }
}
