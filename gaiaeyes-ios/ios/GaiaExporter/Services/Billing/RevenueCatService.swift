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

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "Missing REVENUECAT_IOS_API_KEY in Info.plist."
        case .missingProductIDs:
            return "Missing RevenueCat product identifiers in Info.plist."
        case .productUnavailable(let planID):
            return "RevenueCat product is not available for \(planID)."
        }
    }
}

@MainActor
final class RevenueCatService: ObservableObject {
    static let shared = RevenueCatService()

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
        guard let appUserID, !appUserID.isEmpty else { return }
        do {
            try configureIfNeeded(appUserID: appUserID)
            guard configuredAppUserID != appUserID else {
                return
            }
            let customerInfo = try await logIn(appUserID: appUserID)
            configuredAppUserID = appUserID
            apply(customerInfo: customerInfo)
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
        apply(customerInfo: result.customerInfo)
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
        guard isConfigured else { return }
        do {
            let customerInfo = try await Purchases.shared.logOut()
            configuredAppUserID = nil
            apply(customerInfo: customerInfo)
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
}
