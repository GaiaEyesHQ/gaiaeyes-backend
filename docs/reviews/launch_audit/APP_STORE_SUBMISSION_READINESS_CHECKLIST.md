# Gaia Eyes App Store Submission Readiness Checklist

Last updated: 2026-04-12

This checklist tracks the pieces already shipped in the repo versus the remaining live configuration and App Store Connect setup needed before Gaia Eyes iOS submission.

## Public URLs to use in App Store Connect

- Support URL: `https://gaiaeyes.com/support/`
- Privacy Policy URL: `https://gaiaeyes.com/privacy/`
- Marketing URL: `https://gaiaeyes.com/`
- Terms of Use reference URL: `https://gaiaeyes.com/terms/`

Notes:
- Apple requires a Privacy Policy URL for iOS apps.
- Apple requires in-app account deletion if the app supports account creation.
- Apple provides a standard EULA by default. Use the Gaia Eyes Terms only if choosing to provide a custom agreement or if you want a public legal reference URL in reviewer materials.
- Marketing URL is optional in App Store Connect, but the homepage is safe to use unless a dedicated launch landing page is created before submission.

## App Store Connect fields that should stay off for Gaia Eyes

- Routing App Coverage File: not applicable. Gaia Eyes is not a routing app that provides point-to-point directions for Maps, and the iOS project does not declare routing modes. If App Store Connect requires this field, the app record/category/capability is configured incorrectly; do not upload a fake coverage `.geojson`.
- App Clip: not implemented. The current Xcode project does not include an App Clip target, so App Store Connect cannot configure App Clip experiences until a build containing an App Clip is uploaded. Do not enable App Clip metadata for this submission unless a real clip target is added.
- Apple Watch screenshots: not required unless a watchOS app is included. The current project has no watchOS target, so use iPhone and iPad screenshots only.

## Already implemented in the product

### Public website

- Public support page at `/support/`
- Public privacy policy at `/privacy/`
- Public terms page at `/terms/` with aliases handled for `/terms-of-use/` and `/eula/`
- Support page links to privacy and terms
- Privacy page links to support and terms
- Terms page links to support and privacy

### iOS app

- In-app Help Center
- Direct Settings entry to Help Center
- Direct Settings links to:
  - public support page
  - privacy policy
  - terms of use
- In-app delete-account flow
- Non-destructive delete-account preflight

### Website member hub

- Member Settings section includes:
  - safe delete preflight
  - delete account
  - help center link
  - privacy policy link
  - terms of use link

## Live backend configuration still required

These are the main live blockers that must be configured on the deployed backend before trusting account deletion for review:

- `SUPABASE_URL` or a derivable `SUPABASE_DB_URL`
- `SUPABASE_SERVICE_ROLE_KEY` or `SUPABASE_SERVICE_KEY`

Why they matter:
- delete-account preflight checks them
- real account deletion depends on them
- without them, the flow correctly reports setup issues instead of deleting anything

See:
- [ENVIRONMENT_VARIABLES.md](/Users/jenniferobrien/Documents/GitHub/gaiaeyes-backend/docs/ENVIRONMENT_VARIABLES.md)

## App Store Connect tasks still to complete

### Required

- Set the Support URL to `https://gaiaeyes.com/support/`
- Set the Privacy Policy URL to `https://gaiaeyes.com/privacy/`
- Set the Marketing URL to `https://gaiaeyes.com/` unless a dedicated app landing page is published first
- Complete App Privacy nutrition-label answers to match actual Gaia Eyes data handling
- Verify account deletion can be initiated from inside the app on the build you submit
- Provide App Review sign-in credentials for a non-real-user demo account that does not expire
- Include reviewer notes explaining HealthKit can be skipped or granted, Plus-gated areas are reviewable through the demo account, and Gaia Eyes is wellness/pattern support rather than diagnosis

### Optional but recommended

- Add `https://gaiaeyes.com/terms/` to reviewer notes if you want reviewers to see the public legal terms directly
- If you intend to use a custom EULA instead of Apple’s default, enter the custom agreement in App Store Connect and ensure it matches the public terms page
- Provide a user privacy choices URL only if you decide to maintain a dedicated public privacy-choices page; this is optional

## Reviewer sanity checks before submission

1. Open the app and confirm Help & Support shows:
   - Open Help Center
   - Public Support Page
   - Privacy Policy
   - Terms of Use
2. Open the app Settings > Account & Membership:
   - run safe preflight
   - confirm it reports `Ready...` on a properly configured backend
3. Confirm delete-account can be initiated from inside the app
4. Open these public URLs in a logged-out browser:
   - `/support/`
   - `/privacy/`
   - `/terms/`
5. Confirm the support page contains working contact information and legal/help links
6. Confirm the app Help Center buttons open the public URLs successfully

## App Review demo account recommendation

Create one production-like review account with non-sensitive seed data:

- Email: use a dedicated address such as `appreview@gaiaeyes.com`
- Password: create a unique password only for App Review
- Entitlement: grant Plus in the backend/RevenueCat or make sure the subscription products are submitted with this app version so Apple can review the paywall and gated screens
- Data: use synthetic symptoms/preferences and no personal Health data

Reviewer notes should say the reviewer can continue through onboarding without granting HealthKit, location can be entered by ZIP code, and local/health personalization may be saved on-device if network auth is unavailable during setup.

## App Privacy answer guidance

- Account, profile/preferences, optional symptoms, optional HealthKit-derived samples, optional location/local insight settings, subscription status, diagnostics tied to the account, and support/bug submissions should be disclosed as linked to the user's identity when stored under the Gaia Eyes account/user ID.
- Use purposes should include app functionality and personalization where applicable. Diagnostics should include app functionality and diagnostics; mark linked to identity if logs or reports include account IDs, email, device identifiers, or user-specific state.
- Do not mark third-party tracking unless Gaia Eyes or its SDKs use data to track users across other companies' apps/websites for advertising or data-broker purposes. Infrastructure providers such as hosting, database, billing, and auth are service providers, not tracking by themselves.

## Known non-code questions before submission

- Do we want a business mailing address and/or support phone number surfaced on the public support page, depending on the local-law expectations for the support URL?
- Do we want to rely on Apple’s default EULA, or explicitly configure a custom EULA in App Store Connect?
- Are the live backend env vars for delete-account already present in production, not just locally?
