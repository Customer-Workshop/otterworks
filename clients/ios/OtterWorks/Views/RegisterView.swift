import SwiftUI

struct RegisterView: View {
    @StateObject private var viewModel: AuthViewModel
    @State private var displayName = ""
    @State private var email = ""
    @State private var password = ""

    init(api: OtterWorksAPIClient, session: SessionStore) {
        _viewModel = StateObject(wrappedValue: AuthViewModel(api: api, session: session))
    }

    var body: some View {
        Form {
            Section {
                TextField("Display name", text: $displayName)
                    .textContentType(.name)
                TextField("Email", text: $email)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField("Password (min 8 characters)", text: $password)
                    .textContentType(.newPassword)
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
                        if viewModel.isBusy { ProgressView() } else { Text("Create account") }
                        Spacer()
                    }
                }
                .disabled(!canSubmit)
            }
        }
        .navigationTitle("Register")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var canSubmit: Bool {
        !viewModel.isBusy && !displayName.isEmpty && !email.isEmpty && password.count >= 8
    }

    private func submit() {
        Task {
            await viewModel.register(displayName: displayName, email: email, password: password)
        }
    }
}
