import SwiftUI

struct SubscribeView: View {
    let guideProfile: GuideProfile?
    let helpContext: HelpCenterContext

    @EnvironmentObject var auth: AuthManager
    @Environment(\.openURL) private var openURL
    @StateObject private var revenueCat = RevenueCatService.shared
    @AppStorage("gaia.membership.cached_plan") private var cachedPlanRaw: String = MembershipPlan.free.rawValue
    @AppStorage("gaia.membership.last_sync_at") private var cachedPlanSyncedAt: String = ""

    @State private var errorMessage: String? = nil
    @State private var isWorking = false
    @State private var entitlements: [Entitlement] = []
    @State private var entitlementsLoading = false

    private let appleSubscriptionsURL = URL(string: "https://apps.apple.com/account/subscriptions")

    init(
        guideProfile: GuideProfile? = nil,
        helpContext: HelpCenterContext = HelpCenterContext()
    ) {
        self.guideProfile = guideProfile
        self.helpContext = helpContext
    }

    private var activeBackendEntitlements: [Entitlement] {
        entitlements.filter { $0.isActive == true }
    }

    private var currentPlan: MembershipPlan {
        guard auth.supabaseAccessToken != nil else {
            return .free
        }
        if revenueCat.activePlan != .free {
            return revenueCat.activePlan
        }
        if activeBackendEntitlements.contains(where: { $0.key.lowercased().contains("pro") }) {
            return .pro
        }
        if activeBackendEntitlements.contains(where: { $0.key.lowercased().contains("plus") }) {
            return .plus
        }
        return MembershipPlan(rawValue: cachedPlanRaw) ?? .free
    }

    private var signedInLabel: String {
        if let email = auth.signedInEmail {
            return "Signed in as \(email)"
        }
        if auth.hasAppOnlyProfile {
            return "Using free app profile on this device"
        }
        return "Not signed in on this device"
    }

    private var activeAccessLabels: [String] {
        var labels: [String] = []
        for entitlementID in revenueCat.activeEntitlementIDs {
            labels.append("\(entitlementID.replacingOccurrences(of: "_", with: " ").capitalized) via App Store")
        }
        for entitlement in activeBackendEntitlements {
            labels.append(formattedEntitlement(entitlement))
        }
        var seen = Set<String>()
        return labels.filter { seen.insert($0).inserted }
    }

    private var plusOptionsSummary: String {
        if revenueCat.productOptions["plus_monthly"] != nil && revenueCat.productOptions["plus_yearly"] != nil {
            return "Plus options are ready."
        }
        if revenueCat.productOptions.isEmpty {
            return "Loading Plus options..."
        }
        return "Some Plus options are still loading."
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
                    Text("Sign in to manage plans, purchases, and restore access on this device.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                    freePlanCards
                } else if auth.hasAppOnlyProfile {
                    appOnlyProfileCard
                    LoginView()
                    Text("Add an email and password when you want website access or to restore this account on another device.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                    currentPlanCard
                    planActions

                    if let appleSubscriptionsURL {
                        Button {
                            openURL(appleSubscriptionsURL)
                        } label: {
                            Label("Manage App Store Subscriptions", systemImage: "creditcard")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }

                    Button("Restore Purchases") {
                        Task { await restorePurchases() }
                    }
                    .buttonStyle(.bordered)
                } else {
                    currentPlanCard
                    planActions

                    if !activeAccessLabels.isEmpty {
                        entitlementSummary
                    }

                    if let appleSubscriptionsURL {
                        Button {
                            openURL(appleSubscriptionsURL)
                        } label: {
                            Label("Manage App Store Subscriptions", systemImage: "creditcard")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                    }

                    Button("Restore Purchases") {
                        Task { await restorePurchases() }
                    }
                    .buttonStyle(.bordered)

                    Button("Sign Out") {
                        Task {
                            await revenueCat.logOutIfConfigured()
                            auth.signOutSupabase()
                        }
                    }
                    .buttonStyle(.bordered)
                }

                if isWorking || entitlementsLoading {
                    ProgressView()
                }

                if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .foregroundColor(.orange)
                        .font(.footnote)
                } else if let revenueCatError = revenueCat.lastError, !revenueCatError.isEmpty {
                    Text(revenueCatError)
                        .foregroundColor(.orange)
                        .font(.footnote)
                }

                helpCard
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding()
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
                Text(plusOptionsSummary)
                    .font(.caption)
                    .foregroundColor(.secondary)
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

    private var appOnlyProfileCard: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 6) {
                Text("Free app profile")
                    .font(.subheadline.weight(.semibold))
                Text("Gaia uses a private on-device sync profile so Health data, symptoms, and settings can work before you create a login.")
                    .font(.footnote)
                    .foregroundColor(.secondary)
                Text("This is not an email account yet.")
                    .font(.caption)
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
                    Text("Plus is active")
                        .font(.subheadline.weight(.semibold))
                    Text("Renewals and cancellations are managed through Apple Subscriptions.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        case .pro:
            GroupBox {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Pro is active on this account.")
                        .font(.subheadline.weight(.semibold))
                    Text("Renewals and cancellations are managed through Apple Subscriptions.")
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
                primaryTitle: "Monthly",
                primaryPlan: "plus_monthly",
                secondaryTitle: "Yearly",
                secondaryPlan: "plus_yearly"
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
                    Text("Use the same sign-in you purchased with to restore access on this device.")
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
                    purchaseButton(title: primaryTitle, planID: primaryPlan)
                    purchaseButton(title: secondaryTitle, planID: secondaryPlan)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func purchaseButton(title: String, planID: String) -> some View {
        let option = revenueCat.productOptions[planID]
        Button {
            Task { await purchase(planID: planID) }
        } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                    Text(planID.contains("yearly") ? "Best value annual access" : "Flexible monthly access")
                        .font(.caption2)
                        .foregroundColor(.white.opacity(0.82))
                }
                Spacer()
                if let option {
                    Text(option.price)
                        .font(.headline.weight(.bold))
                } else {
                    Text("Loading")
                        .font(.caption.weight(.semibold))
                }
            }
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .disabled(isWorking || option == nil)
    }

    private var entitlementSummary: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 6) {
                Text("Current Access")
                    .font(.subheadline.weight(.semibold))
                ForEach(activeAccessLabels, id: \.self) { label in
                    Text(label)
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

    private func purchase(planID: String) async {
        errorMessage = nil
        isWorking = true
        defer { isWorking = false }

        guard auth.supabaseAccessToken != nil else {
            errorMessage = "Sign-in required."
            return
        }
        guard let userID = await auth.resolveSupabaseUserId(), !userID.isEmpty else {
            errorMessage = "Could not resolve your signed-in user before purchase."
            return
        }

        do {
            let plan = try await revenueCat.purchase(planID: planID, appUserID: userID)
            cachedPlanRaw = plan.rawValue
            cachedPlanSyncedAt = ISO8601DateFormatter().string(from: Date())
            errorMessage = "\(plan.title) is active."
            await refreshBackendEntitlementsAfterRevenueCatUpdate()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func restorePurchases() async {
        errorMessage = nil
        isWorking = true
        defer { isWorking = false }

        let userID = await auth.resolveSupabaseUserId()

        do {
            let plan = try await revenueCat.restore(appUserID: userID)
            cachedPlanRaw = plan.rawValue
            cachedPlanSyncedAt = ISO8601DateFormatter().string(from: Date())
            errorMessage = plan == .free ? "No active App Store subscription was found for this Apple ID." : "\(plan.title) access restored."
            await refreshBackendEntitlementsAfterRevenueCatUpdate()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func refreshBackendEntitlementsAfterRevenueCatUpdate() async {
        try? await Task.sleep(nanoseconds: 2_000_000_000)
        await refreshEntitlementsIfNeeded()
    }

    private func refreshEntitlementsIfNeeded() async {
        errorMessage = nil
        guard let token = auth.supabaseAccessToken else {
            entitlements = []
            cachedPlanRaw = MembershipPlan.free.rawValue
            return
        }

        let userID = await auth.resolveSupabaseUserId()
        await revenueCat.identifyIfNeeded(appUserID: userID)
        await revenueCat.refreshProducts(appUserID: userID)
        await revenueCat.refreshCustomerInfo(appUserID: userID)

        entitlementsLoading = true
        defer { entitlementsLoading = false }
        do {
            let service = try CheckoutService()
            let response = try await service.fetchEntitlements(accessToken: token)
            entitlements = response.entitlements
            cachedPlanRaw = currentPlan.rawValue
            cachedPlanSyncedAt = ISO8601DateFormatter().string(from: Date())
        } catch {
            if revenueCat.activePlan == .free {
                errorMessage = error.localizedDescription
            }
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
