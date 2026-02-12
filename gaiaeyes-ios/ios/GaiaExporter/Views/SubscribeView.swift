import SwiftUI
import SafariServices

struct SubscribeView: View {
    @EnvironmentObject var auth: AuthManager
    @State private var checkoutURL: URL? = nil
    @State private var showSafari = false
    @State private var errorMessage: String? = nil
    @State private var isWorking = false
    @State private var entitlements: [Entitlement] = []
    @State private var entitlementsLoading = false

    private let billingPortalURL = Bundle.main.object(forInfoDictionaryKey: "GAIA_BILLING_PORTAL_URL") as? String

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text("Subscribe")
                    .font(.title2)

                if !auth.isConfigured {
                    Text("Missing SUPABASE_URL or SUPABASE_ANON_KEY in Info.plist.")
                        .font(.footnote)
                        .foregroundColor(.orange)
                }

                if auth.supabaseAccessToken == nil {
                    LoginView()
                } else {
                    if let email = auth.supabaseEmail {
                        Text("Signed in as \(email)")
                            .font(.footnote)
                            .foregroundColor(.secondary)
                    }

                    VStack(spacing: 12) {
                        Button("Get Plus (Monthly)") { Task { await startCheckout(plan: "plus_monthly") } }
                            .buttonStyle(.borderedProminent)
                        Button("Get Plus (Yearly)") { Task { await startCheckout(plan: "plus_yearly") } }
                            .buttonStyle(.bordered)
                        Button("Get Pro (Monthly)") { Task { await startCheckout(plan: "pro_monthly") } }
                            .buttonStyle(.borderedProminent)
                        Button("Get Pro (Yearly)") { Task { await startCheckout(plan: "pro_yearly") } }
                            .buttonStyle(.bordered)
                    }
                    .disabled(isWorking)

                    if let portal = billingPortalURL, let portalURL = URL(string: portal) {
                        Button("Manage Billing") {
                            checkoutURL = portalURL
                            showSafari = true
                        }
                        .buttonStyle(.bordered)
                    }

                    if entitlementsLoading {
                        ProgressView()
                    } else if !entitlements.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Current Entitlements")
                                .font(.headline)
                            ForEach(entitlements.indices, id: \.self) { idx in
                                let ent = entitlements[idx]
                                Text("\(ent.key) \(ent.term ?? "") - \(ent.isActive == true ? "active" : "inactive")")
                                    .font(.footnote)
                            }
                        }
                    }

                    Button("Sign Out") { auth.signOutSupabase() }
                        .buttonStyle(.bordered)
                }

                if isWorking {
                    ProgressView()
                }

                if let errorMessage {
                    Text(errorMessage)
                        .foregroundColor(.orange)
                        .font(.footnote)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
        }
        .sheet(isPresented: $showSafari) {
            if let url = checkoutURL {
                SafariView(url: url)
            }
        }
        .task {
            await refreshEntitlementsIfNeeded()
        }
        .onChange(of: auth.supabaseAccessToken) { _ in
            Task { await refreshEntitlementsIfNeeded() }
        }
    }

    private func startCheckout(plan: String) async {
        errorMessage = nil
        isWorking = true
        defer { isWorking = false }

        guard let token = auth.supabaseAccessToken else {
            errorMessage = "Sign-in required."
            return
        }

        do {
            let service = try CheckoutService()
            let url = try await service.startCheckout(plan: plan, accessToken: token)
            checkoutURL = url
            showSafari = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func refreshEntitlementsIfNeeded() async {
        guard let token = auth.supabaseAccessToken else { return }
        entitlementsLoading = true
        defer { entitlementsLoading = false }
        do {
            let service = try CheckoutService()
            let response = try await service.fetchEntitlements(accessToken: token)
            entitlements = response.entitlements
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct SafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        SFSafariViewController(url: url)
    }

    func updateUIViewController(_ uiViewController: SFSafariViewController, context: Context) {}
}
