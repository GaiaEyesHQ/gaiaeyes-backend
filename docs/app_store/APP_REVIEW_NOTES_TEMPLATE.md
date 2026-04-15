# Gaia Eyes App Review Notes Template

Use this in App Store Connect’s App Review Information fields. Replace placeholders before submission.

## Contact Information

- Contact: Jennifer O’Brien
- Email: [use App Store Connect contact email]
- Phone: [use App Store Connect contact phone]

## Demo Account

Create a dedicated Supabase password account for review. Do not use a personal or developer account.

- Email: `[app-review-email]`
- Password: `[temporary-review-password]`
- Plan: Plus enabled
- Health data: seeded synthetic or scrubbed non-personal data
- Notifications: off unless you want App Review to test notices
- Location: ZIP-based location set to a normal test ZIP
- Experience mode: Scientific or Balanced, unless you specifically want Apple to see Mystical copy

Recommended account setup:

- Complete onboarding before submission.
- Give the reviewer account enough seeded samples to show gauges, drivers, outlook, and patterns.
- Add a few symptom logs so the app does not look empty.
- Avoid real personal notes, real medical details, or personal HealthKit data.

## Review Notes

Suggested text:

> Gaia Eyes is a wellness and environmental-context app. It combines user-provided symptoms, optional Apple Health data, local environmental signals, and space-weather/earth-resonance data to provide non-diagnostic daily context. It does not provide medical advice, diagnosis, or treatment.
>
> The demo account above has Plus enabled and seeded test data so reviewers can see the full app experience without connecting a personal HealthKit account. HealthKit permissions are optional during onboarding. If HealthKit is skipped, the app still shows public environmental and space-weather context.
>
> In-app subscriptions are managed through Apple In-App Purchase via RevenueCat. Existing web subscribers can sign in, but iOS purchase flow uses Apple IAP.

## Optional Attachments

Minimum recommended attachment set:

- One short demo video showing onboarding, Home, Guide, Drivers, Patterns, Outlook, and Account & Membership.
- One screenshot of the Plus purchase screen if App Store Connect asks for subscription review support.

Do not attach backend credentials, Supabase keys, RevenueCat secrets, Stripe secrets, or internal logs.

