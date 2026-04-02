import SwiftUI
import SafariServices

struct SubscribeView: View {
    let guideProfile: GuideProfile?
    let helpContext: HelpCenterContext

    @EnvironmentObject var auth: AuthManager
    @AppStorage("gaia.membership.cached_plan") private var cachedPlanRaw: String = MembershipPlan.free.rawValue
    @AppStorage("gaia.membership.last_sync_at") private var cachedPlanSyncedAt: String = ""

    @State private var checkoutURL: URL? = nil
    @State private var showSafari = false
    @State private var errorMessage: String? = nil
    @State private var isWorking = false
    @State private var entitlements: [Entitlement] = []
    @State private var entitlementsLoading = false

    private let billingPortalURL = Bundle.main.object(forInfoDictionaryKey: "GAIA_BILLING_PORTAL_URL") as? String

    init(
        guideProfile: GuideProfile? = nil,
        helpContext: HelpCenterContext = HelpCenterContext()
    ) {
        self.guideProfile = guideProfile
        self.helpContext = helpContext
    }

    private var activeEntitlements: [Entitlement] {
        entitlements.filter { $0.isActive == true }
    }

    private var currentPlan: MembershipPlan {
        guard auth.supabaseAccessToken != nil else {
            return .free
        }
        if activeEntitlements.contains(where: { $0.key.lowercased().contains("pro") }) {
            return .pro
        }
        if activeEntitlements.contains(where: { $0.key.lowercased().contains("plus") }) {
            return .plus
        }
        return MembershipPlan(rawValue: cachedPlanRaw) ?? .free
    }

    private var signedInLabel: String {
        if let email = auth.supabaseEmail, !email.isEmpty {
            return "Signed in as \(email)"
        }
        if let userId = auth.currentSupabaseUserId() {
            return "Signed in as \(userId.prefix(8))..."
        }
        return "Signed in on this device"
    }

    private var canManageBilling: Bool {
        currentPlan != .free && billingPortalResolvedURL != nil
    }

    private var billingPortalResolvedURL: URL? {
        guard let billingPortalURL else { return nil }
        return URL(string: billingPortalURL)
    }

    private var resolvedHelpContext: HelpCenterContext {
        var context = helpContext
        if context.guideProfile == nil {
            context.guideProfile = guideProfile
        }
        return context
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Account & Membership")
                    .font(.title2.weight(.bold))

                if !auth.isConfigured {
                    Text("Missing SUPABASE_URL or SUPABASE_ANON_KEY in Info.plist.")
                        .font(.footnote)
                        .foregroundColor(.orange)
                }

                statusCard

                if auth.supabaseAccessToken == nil {
                    LoginView()
                    Text("Sign in to manage plans, billing, and future purchases on this device.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                    freePlanCards
                } else {
                    currentPlanCard
                    planActions

                    if !activeEntitlements.isEmpty {
                        entitlementSummary
                    }

                    if canManageBilling, let portal = billingPortalResolvedURL {
                        Button("Manage Billing") {
                            checkoutURL = portal
                            showSafari = true
                        }
                        .buttonStyle(.bordered)
                    }

                    Button("Restore Purchases") {
                        Task { await refreshMembershipStatus() }
                    }
                    .buttonStyle(.bordered)

                    Button("Sign Out") { auth.signOutSupabase() }
                        .buttonStyle(.bordered)
                }

                if isWorking || entitlementsLoading {
                    ProgressView()
                }

                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .foregroundColor(.orange)
                        .font(.footnote)
                }

                helpCard
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
            await refreshMembershipStatus()
        }
        .onChange(of: auth.supabaseAccessToken) { _, _ in
            Task { await refreshEntitlementsIfNeeded() }
        }
    }

    private var statusCard: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline) {
                    Text(auth.supabaseAccessToken == nil ? "Status: Not signed in on this device" : signedInLabel)
                        .font(.footnote)
                        .foregroundColor(.secondary)
                    Spacer()
                    Button("Refresh Status") {
                        Task { await refreshMembershipStatus() }
                    }
                    .font(.caption)
                }
                Text("Your Plan: \(currentPlan.title)")
                    .font(.headline)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var currentPlanCard: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 6) {
                Text("Your Plan")
                    .font(.subheadline.weight(.semibold))
                Text(currentPlan.title)
                    .font(.title3.weight(.bold))
                Text(planDescription(for: currentPlan))
                    .font(.footnote)
                    .foregroundColor(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private var planActions: some View {
        switch currentPlan {
        case .free:
            freePlanCards
        case .plus:
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Upgrade to Pro")
                        .font(.subheadline.weight(.semibold))
                    Text("Keep your current Plus access and move up when you want deeper outlooks and premium intelligence layers.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                    Button("Upgrade to Pro (Monthly)") {
                        Task { await startCheckout(plan: "pro_monthly") }
                    }
                    .buttonStyle(.borderedProminent)
                    Button("Upgrade to Pro (Yearly)") {
                        Task { await startCheckout(plan: "pro_yearly") }
                    }
                    .buttonStyle(.bordered)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .disabled(isWorking)
        case .pro:
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Pro is active on this account.")
                        .font(.subheadline.weight(.semibold))
                    Text("Billing and renewal changes stay available in Manage Billing.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var freePlanCards: some View {
        VStack(spacing: 12) {
            planCard(
                title: "Plus",
                description: "Unlock richer current-state personalization, better drivers, and more useful day-to-day signal context.",
                primaryTitle: "Get Plus (Monthly)",
                primaryPlan: "plus_monthly",
                secondaryTitle: "Get Plus (Yearly)",
                secondaryPlan: "plus_yearly"
            )

            planCard(
                title: "Pro",
                description: "Add deeper outlooks, advanced history, premium notifications, and a more complete intelligence layer.",
                primaryTitle: "Get Pro (Monthly)",
                primaryPlan: "pro_monthly",
                secondaryTitle: "Get Pro (Yearly)",
                secondaryPlan: "pro_yearly"
            )
        }
    }

    private var helpCard: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                Text("Need help with billing, restore access, Health sync, or privacy questions?")
                    .font(.footnote)
                    .foregroundColor(.secondary)
                NavigationLink(destination: HelpCenterView(context: resolvedHelpContext)) {
                    Label("Open Help Center", systemImage: "questionmark.circle")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)

                if auth.supabaseAccessToken == nil {
                    Text("Use the same sign-in you checked out with to restore access on this device.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func planCard(
        title: String,
        description: String,
        primaryTitle: String,
        primaryPlan: String,
        secondaryTitle: String,
        secondaryPlan: String
    ) -> some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                Text(title)
                    .font(.headline)
                Text(description)
                    .font(.footnote)
                    .foregroundColor(.secondary)
                if auth.supabaseAccessToken == nil {
                    Text("Sign in to purchase this plan.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                } else {
                    Button(primaryTitle) {
                        Task { await startCheckout(plan: primaryPlan) }
                    }
                    .buttonStyle(.borderedProminent)
                    Button(secondaryTitle) {
                        Task { await startCheckout(plan: secondaryPlan) }
                    }
                    .buttonStyle(.bordered)
                    .disabled(isWorking)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var entitlementSummary: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 6) {
                Text("Current Access")
                    .font(.subheadline.weight(.semibold))
                ForEach(activeEntitlements.indices, id: \.self) { idx in
                    let ent = activeEntitlements[idx]
                    Text(formattedEntitlement(ent))
                        .font(.footnote)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func planDescription(for plan: MembershipPlan) -> String {
        switch plan {
        case .free:
            return "Free keeps the core experience available while you decide how personal you want Gaia Eyes to become."
        case .plus:
            return "Plus focuses on current-state personalization and more useful daily context."
        case .pro:
            return "Pro unlocks the full premium intelligence layer."
        }
    }

    private func formattedEntitlement(_ entitlement: Entitlement) -> String {
        let label = entitlement.key.replacingOccurrences(of: "_", with: " ").capitalized
        if let term = entitlement.term, !term.isEmpty {
            return "\(label) • \(term.capitalized)"
        }
        return label
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
        errorMessage = nil
        guard let token = auth.supabaseAccessToken else {
            entitlements = []
            cachedPlanRaw = MembershipPlan.free.rawValue
            return
        }
        entitlementsLoading = true
        defer { entitlementsLoading = false }
        do {
            let service = try CheckoutService()
            let response = try await service.fetchEntitlements(accessToken: token)
            entitlements = response.entitlements
            cachedPlanRaw = currentPlan.rawValue
            cachedPlanSyncedAt = ISO8601DateFormatter().string(from: Date())
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func refreshMembershipStatus() async {
        await refreshSessionStatus()
        await refreshEntitlementsIfNeeded()
    }

    private func refreshSessionStatus() async {
        auth.loadFromKeychain()
        _ = await auth.validAccessToken()
        _ = await auth.resolveSupabaseUserId()
    }
}

struct SafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        SFSafariViewController(url: url)
    }

    func updateUIViewController(_ uiViewController: SFSafariViewController, context: Context) {}
}
