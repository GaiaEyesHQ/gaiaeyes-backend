import SwiftUI

struct LoginView: View {
    @EnvironmentObject var auth: AuthManager
    let initialEmail: String?
    let onAuthenticated: (() -> Void)?

    @State private var email: String = ""
    @State private var password: String = ""
    @State private var isCreateMode: Bool = false
    @State private var isBusy: Bool = false
    @State private var errorMessage: String?
    @State private var successMessage: String?

    init(initialEmail: String? = nil, onAuthenticated: (() -> Void)? = nil) {
        self.initialEmail = initialEmail
        self.onAuthenticated = onAuthenticated
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(isCreateMode ? "Create account" : "Sign in to continue")
                .font(.headline)

            TextField("Email", text: $email)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .disableAutocorrection(true)
                .textFieldStyle(.roundedBorder)

            SecureField("Password", text: $password)
                .textContentType(isCreateMode ? .newPassword : .password)
                .textFieldStyle(.roundedBorder)

            Button(isCreateMode ? "Create Account" : "Sign In") {
                Task { await submit() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(isBusy || email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || password.isEmpty)

            Button(isCreateMode ? "Already have an account? Sign in" : "Create an account") {
                isCreateMode.toggle()
                errorMessage = nil
                successMessage = nil
            }
            .font(.footnote.weight(.semibold))
            .buttonStyle(.plain)
            .foregroundColor(Color(red: 0.45, green: 0.72, blue: 1.0))

            if let successMessage {
                Text(successMessage)
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundColor(.orange)
            }
        }
        .onAppear {
            guard email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
            email = initialEmail?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        }
    }

    private func submit() async {
        errorMessage = nil
        successMessage = nil
        isBusy = true
        defer { isBusy = false }

        do {
            if isCreateMode {
                let signedIn = try await auth.createAccountWithPassword(email: email, password: password)
                successMessage = signedIn
                    ? "Account created."
                    : "Check your email to verify the account, then sign in here."
                if signedIn {
                    onAuthenticated?()
                }
            } else {
                try await auth.signInWithPassword(email: email, password: password)
                successMessage = "Signed in."
                onAuthenticated?()
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
