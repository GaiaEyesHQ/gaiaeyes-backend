import SwiftUI

struct LoginView: View {
    @EnvironmentObject var auth: AuthManager
    @State private var email: String = ""
    @State private var sent: Bool = false
    @State private var isBusy: Bool = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Sign in to continue")
                .font(.headline)

            TextField("Email", text: $email)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .disableAutocorrection(true)
                .textFieldStyle(.roundedBorder)

            Button("Send Magic Link") {
                Task { await sendMagicLink() }
            }
            .buttonStyle(.borderedProminent)
            .disabled(isBusy || email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)

            if sent {
                Text("Check your email for the magic link, then return to the app.")
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }

            if let errorMessage {
                Text(errorMessage)
                    .font(.footnote)
                    .foregroundColor(.orange)
            }
        }
    }

    private func sendMagicLink() async {
        errorMessage = nil
        sent = false
        isBusy = true
        defer { isBusy = false }

        do {
            try await auth.signInSupabase(email: email)
            sent = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
