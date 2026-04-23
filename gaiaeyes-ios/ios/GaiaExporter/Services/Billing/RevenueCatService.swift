import Foundation
import RevenueCat

struct RevenueCatProductOption: Identifiable {
    let id: String
    let planID: String
    let title: String
    let price: String
    let product: StoreProduct
}

private struct RevenueCatBillingConfig {
    let apiKey: String
    let plusEntitlementID: String
    let proEntitlementID: String
    let productIDsByPlan: [String: String]

    static func load() throws -> RevenueCatBillingConfig {
        let bundle = Bundle.main
        guard let apiKey = clean(bundle.object(forInfoDictionaryKey: "REVENUECAT_IOS_API_KEY") as? String) else {
            throw RevenueCatBillingError.missingAPIKey
        }

        let productIDsByPlan = [
            "plus_monthly": clean(bundle.object(forInfoDictionaryKey: "REVENUECAT_PLUS_MONTHLY_PRODUCT_ID") as? String),
            "plus_yearly": clean(bundle.object(forInfoDictionaryKey: "REVENUECAT_PLUS_YEARLY_PRODUCT_ID") as? String),
            "pro_monthly": clean(bundle.object(forInfoDictionaryKey: "REVENUECAT_PRO_MONTHLY_PRODUCT_ID") as? String),
            "pro_yearly": clean(bundle.object(forInfoDictionaryKey: "REVENUECAT_PRO_YEARLY_PRODUCT_ID") as? String),
        ].compactMapValues { $0 }

        guard !productIDsByPlan.isEmpty else {
            throw RevenueCatBillingError.missingProductIDs
        }

        return RevenueCatBillingConfig(
            apiKey: apiKey,
            plusEntitlementID: clean(bundle.object(forInfoDictionaryKey: "REVENUECAT_PLUS_ENTITLEMENT_ID") as? String) ?? "plus",
            proEntitlementID: clean(bundle.object(forInfoDictionaryKey: "REVENUECAT_PRO_ENTITLEMENT_ID") as? String) ?? "pro",
            productIDsByPlan: productIDsByPlan
        )
    }

    func planID(for productID: String) -> String? {
        productIDsByPlan.first(where: { $0.value == productID })?.key
    }

    private static func clean(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty,
              !trimmed.hasPrefix("$(") else {
            return nil
        }
        return trimmed
    }
}

enum RevenueCatBillingError: LocalizedError {
    case missingAPIKey
    case missingProductIDs
    case productUnavailable(String)
    case purchaseCancelled
    case purchaseDidNotActivate

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "Missing REVENUECAT_IOS_API_KEY in Info.plist."
        case .missingProductIDs:
            return "Missing RevenueCat product identifiers in Info.plist."
        case .productUnavailable(let planID):
            return "RevenueCat product is not available for \(planID)."
        case .purchaseCancelled:
            return "Purchase was cancelled before it completed."
        case .purchaseDidNotActivate:
            return "Purchase finished, but Plus is not active yet. Check that the RevenueCat product is attached to the plus entitlement, then tap Restore Purchases."
        }
    }
}

@MainActor
final class RevenueCatService: ObservableObject {
    static let shared = RevenueCatService()

    private enum CacheKeys {
        static let suiteName = "com.revenuecat.user_defaults"
        static let appUserID = "com.revenuecat.userdefaults.appUserID.new"
        static let legacyAppUserID = "com.revenuecat.userdefaults.appUserID"
        static let subscriberAttributes = "com.revenuecat.userdefaults.subscriberAttributes"
        static let customerInfoPrefix = "com.revenuecat.userdefaults.purchaserInfo."
        static let customerInfoLastUpdatedPrefix = "com.revenuecat.userdefaults.purchaserInfoLastUpdated."
        static let offeringsPrefix = "com.revenuecat.userdefaults.offerings."
        static let legacySubscriberAttributesPrefix = "com.revenuecat.userdefaults.subscriberAttributes."
        static let attributionPrefix = "com.revenuecat.userdefaults.attribution."
        static let virtualCurrenciesPrefix = "com.revenuecat.userdefaults.virtualCurrencies."
        static let virtualCurrenciesLastUpdatedPrefix = "com.revenuecat.userdefaults.virtualCurrenciesLastUpdated."
    }

    @Published private(set) var isConfigured = false
    @Published private(set) var activePlan: MembershipPlan = .free
    @Published private(set) var activeEntitlementIDs: [String] = []
    @Published private(set) var productOptions: [String: RevenueCatProductOption] = [:]
    @Published private(set) var lastSyncAt: Date?
    @Published private(set) var lastError: String?
    @Published private(set) var productFetchStatus = "Not fetched"

    private var config: RevenueCatBillingConfig?
    private var configuredAppUserID: String?

    var diagnosticsState: String {
        if isConfigured {
            return configuredAppUserID.map { "Configured for \($0)" } ?? "Configured anonymously"
        }
        if let lastError, !lastError.isEmpty {
            return "Not configured: \(lastError)"
        }
        return "Not configured"
    }

    var productStatus: String {
        if productOptions.isEmpty {
            return productFetchStatus
        }
        return "Loaded \(productOptions.count) RevenueCat product(s)"
    }

    private init() {}

    func syncIdentity(appUserID: String?, allowLogOut: Bool = true) async {
        guard let normalizedAppUserID = normalizedAppUserID(appUserID) else {
            guard allowLogOut else {
                appLog("[RC] skipped RevenueCat logout while auth session continuity is present")
                return
            }
            await handleSignedOutIdentity()
            return
        }

        await identifyIfNeeded(appUserID: normalizedAppUserID)
    }

    func configureIfNeeded(appUserID: String? = nil) throws {
        if isConfigured {
            return
        }
        let loadedConfig = try RevenueCatBillingConfig.load()
        #if DEBUG
        Purchases.logLevel = .debug
        #else
        Purchases.logLevel = .warn
        #endif
        Purchases.configure(withAPIKey: loadedConfig.apiKey, appUserID: appUserID)
        config = loadedConfig
        configuredAppUserID = appUserID
        isConfigured = true
        lastError = nil
    }

    func identifyIfNeeded(appUserID: String?) async {
        guard let appUserID = normalizedAppUserID(appUserID) else { return }
        let wasConfigured = isConfigured
        let previousConfiguredAppUserID = configuredAppUserID
        do {
            try configureIfNeeded(appUserID: appUserID)

            guard wasConfigured, previousConfiguredAppUserID != appUserID else {
                pruneCachedState(keepingAppUserIDs: Set([appUserID]), clearStoredCurrentUserID: false)
                return
            }

            let customerInfo = try await logIn(appUserID: appUserID)
            configuredAppUserID = appUserID
            apply(customerInfo: customerInfo)
            pruneCachedState(
                keepingAppUserIDs: Set([currentRevenueCatAppUserID() ?? appUserID]),
                clearStoredCurrentUserID: false
            )
        } catch {
            lastError = error.localizedDescription
        }
    }

    func refreshProducts(appUserID: String? = nil) async {
        productFetchStatus = "Loading RevenueCat products"
        do {
            try configureIfNeeded(appUserID: appUserID)
            guard let config else { throw RevenueCatBillingError.missingProductIDs }
            let products = await Purchases.shared.products(Array(config.productIDsByPlan.values))
            var options: [String: RevenueCatProductOption] = [:]
            for product in products {
                guard let planID = config.planID(for: product.productIdentifier) else { continue }
                options[planID] = RevenueCatProductOption(
                    id: product.productIdentifier,
                    planID: planID,
                    title: product.localizedTitle,
                    price: product.localizedPriceString,
                    product: product
                )
            }
            productOptions = options
            productFetchStatus = options.isEmpty
                ? "No matching RevenueCat products returned"
                : "Loaded \(options.count) RevenueCat product(s)"
            lastError = nil
        } catch {
            productOptions = [:]
            productFetchStatus = "RevenueCat product fetch failed"
            lastError = error.localizedDescription
        }
    }

    func refreshCustomerInfo(appUserID: String? = nil) async {
        do {
            try configureIfNeeded(appUserID: appUserID)
            let customerInfo = try await Purchases.shared.customerInfo()
            apply(customerInfo: customerInfo)
            lastError = nil
        } catch {
            lastError = error.localizedDescription
        }
    }

    @discardableResult
    func purchase(planID: String, appUserID: String?) async throws -> MembershipPlan {
        try configureIfNeeded(appUserID: appUserID)
        if productOptions[planID] == nil {
            await refreshProducts(appUserID: appUserID)
        }
        guard let option = productOptions[planID] else {
            throw RevenueCatBillingError.productUnavailable(planID)
        }
        let result = try await Purchases.shared.purchase(product: option.product)
        if result.userCancelled {
            throw RevenueCatBillingError.purchaseCancelled
        }
        apply(customerInfo: result.customerInfo)
        if activePlan == .free {
            throw RevenueCatBillingError.purchaseDidNotActivate
        }
        return activePlan
    }

    @discardableResult
    func restore(appUserID: String?) async throws -> MembershipPlan {
        try configureIfNeeded(appUserID: appUserID)
        let customerInfo = try await Purchases.shared.restorePurchases()
        apply(customerInfo: customerInfo)
        return activePlan
    }

    func logOutIfConfigured() async {
        guard isConfigured, configuredAppUserID != nil else { return }
        do {
            if let currentAppUserID = currentRevenueCatAppUserID() {
                pruneCachedState(keepingAppUserIDs: Set([currentAppUserID]), clearStoredCurrentUserID: false)
            }
            let customerInfo = try await Purchases.shared.logOut()
            configuredAppUserID = nil
            apply(customerInfo: customerInfo)
            if let currentAppUserID = currentRevenueCatAppUserID() {
                pruneCachedState(keepingAppUserIDs: Set([currentAppUserID]), clearStoredCurrentUserID: false)
            }
        } catch {
            lastError = error.localizedDescription
        }
    }

    private func logIn(appUserID: String) async throws -> CustomerInfo {
        try await withCheckedThrowingContinuation { continuation in
            Purchases.shared.logIn(appUserID) { customerInfo, _, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                guard let customerInfo else {
                    continuation.resume(throwing: RevenueCatBillingError.productUnavailable("customer_info"))
                    return
                }
                continuation.resume(returning: customerInfo)
            }
        }
    }

    private func apply(customerInfo: CustomerInfo) {
        guard let config else { return }
        var activeIDs: [String] = []
        if customerInfo.entitlements[config.plusEntitlementID]?.isActive == true {
            activeIDs.append(config.plusEntitlementID)
        }
        if customerInfo.entitlements[config.proEntitlementID]?.isActive == true {
            activeIDs.append(config.proEntitlementID)
        }
        activeEntitlementIDs = activeIDs
        activePlan = activeIDs.contains(config.proEntitlementID) ? .pro : (activeIDs.contains(config.plusEntitlementID) ? .plus : .free)
        lastSyncAt = Date()
    }

    private func handleSignedOutIdentity() async {
        if isConfigured {
            if configuredAppUserID != nil {
                await logOutIfConfigured()
            } else if let currentAppUserID = currentRevenueCatAppUserID() {
                pruneCachedState(keepingAppUserIDs: Set([currentAppUserID]), clearStoredCurrentUserID: false)
            }
        } else {
            pruneCachedState(keepingAppUserIDs: Set<String>(), clearStoredCurrentUserID: true)
        }

        configuredAppUserID = nil
        activePlan = .free
        activeEntitlementIDs = []
    }

    private func normalizedAppUserID(_ appUserID: String?) -> String? {
        guard let trimmed = appUserID?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else {
            return nil
        }
        return trimmed
    }

    private func currentRevenueCatAppUserID() -> String? {
        guard isConfigured else { return nil }
        return normalizedAppUserID(Purchases.shared.appUserID)
    }

    private func pruneCachedState(keepingAppUserIDs: Set<String>, clearStoredCurrentUserID: Bool) {
        let stores = [UserDefaults.standard, UserDefaults(suiteName: CacheKeys.suiteName)].compactMap { $0 }
        var removedUserIDs = Set<String>()
        for store in stores {
            removedUserIDs.formUnion(
                pruneCachedState(
                    in: store,
                    keepingAppUserIDs: keepingAppUserIDs,
                    clearStoredCurrentUserID: clearStoredCurrentUserID
                )
            )
        }

        guard !removedUserIDs.isEmpty else { return }
        let kept = keepingAppUserIDs.sorted().joined(separator: ",")
        let removed = removedUserIDs.sorted().joined(separator: ",")
        appLog("[RC] pruned cached identities removed=[\(removed)] keep=[\(kept)]")
    }

    private func pruneCachedState(
        in defaults: UserDefaults,
        keepingAppUserIDs: Set<String>,
        clearStoredCurrentUserID: Bool
    ) -> Set<String> {
        var removedUserIDs = Set<String>()

        if let groupedAttributes = defaults.dictionary(forKey: CacheKeys.subscriberAttributes) {
            let filteredAttributes = groupedAttributes.filter { keepingAppUserIDs.contains($0.key) }
            removedUserIDs.formUnion(groupedAttributes.keys.filter { !keepingAppUserIDs.contains($0) })
            if filteredAttributes.isEmpty {
                defaults.removeObject(forKey: CacheKeys.subscriberAttributes)
            } else {
                defaults.set(filteredAttributes, forKey: CacheKeys.subscriberAttributes)
            }
        }

        let userScopedPrefixes = [
            CacheKeys.customerInfoPrefix,
            CacheKeys.customerInfoLastUpdatedPrefix,
            CacheKeys.offeringsPrefix,
            CacheKeys.legacySubscriberAttributesPrefix,
            CacheKeys.attributionPrefix,
            CacheKeys.virtualCurrenciesPrefix,
            CacheKeys.virtualCurrenciesLastUpdatedPrefix,
        ]

        for key in defaults.dictionaryRepresentation().keys {
            guard let prefix = userScopedPrefixes.first(where: { key.hasPrefix($0) }) else { continue }
            let appUserID = String(key.dropFirst(prefix.count))
            guard !appUserID.isEmpty, !keepingAppUserIDs.contains(appUserID) else { continue }
            defaults.removeObject(forKey: key)
            removedUserIDs.insert(appUserID)
        }

        if clearStoredCurrentUserID {
            if let cachedAppUserID = normalizedAppUserID(defaults.string(forKey: CacheKeys.appUserID)) {
                removedUserIDs.insert(cachedAppUserID)
            }
            if let cachedLegacyAppUserID = normalizedAppUserID(defaults.string(forKey: CacheKeys.legacyAppUserID)) {
                removedUserIDs.insert(cachedLegacyAppUserID)
            }
            defaults.removeObject(forKey: CacheKeys.appUserID)
            defaults.removeObject(forKey: CacheKeys.legacyAppUserID)
        }

        return removedUserIDs
    }
}
