# Gaia Eyes App Store Submission Readiness Checklist

Last updated: 2026-04-09

This checklist tracks the pieces already shipped in the repo versus the remaining live configuration and App Store Connect setup needed before Gaia Eyes iOS submission.

## Public URLs to use in App Store Connect

- Support URL: `https://gaiaeyes.com/support/`
- Privacy Policy URL: `https://gaiaeyes.com/privacy/`
- Terms of Use reference URL: `https://gaiaeyes.com/terms/`

Notes:
- Apple requires a Privacy Policy URL for iOS apps.
- Apple requires in-app account deletion if the app supports account creation.
- Apple provides a standard EULA by default. Use the Gaia Eyes Terms only if choosing to provide a custom agreement or if you want a public legal reference URL in reviewer materials.

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

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

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
- Complete App Privacy nutrition-label answers to match actual Gaia Eyes data handling
- Verify account deletion can be initiated from inside the app on the build you submit

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

## Known non-code questions before submission

- Do we want a business mailing address and/or support phone number surfaced on the public support page, depending on the local-law expectations for the support URL?
- Do we want to rely on Apple’s default EULA, or explicitly configure a custom EULA in App Store Connect?
- Are the live backend env vars for delete-account already present in production, not just locally?
