# Gaia Eyes Export Compliance Note

Use this as an internal App Store Connect checklist. Do not upload this file unless App Review specifically asks for encryption documentation.

## Current App Position

Gaia Eyes uses standard Apple platform networking and HTTPS/TLS to communicate with:

- Gaia Eyes backend API
- Supabase Auth, database, and public storage
- RevenueCat
- Apple HealthKit and StoreKit platform services

The app does not implement proprietary encryption algorithms, custom cryptographic protocols, VPN/tunneling, file encryption, end-to-end encrypted messaging, encrypted backups, or cryptographic key management for users.

## App Store Connect Answer

Set `ITSAppUsesNonExemptEncryption` to `false` in `Info.plist`.

In App Store Connect export compliance, answer that the app does not use non-exempt encryption. The app only uses encryption that is exempt under Apple’s standard HTTPS/TLS/platform-services guidance.

## If App Review Asks

Suggested reviewer response:

> Gaia Eyes uses only standard Apple-provided and platform HTTPS/TLS networking for secure communication with its backend, Supabase, RevenueCat, StoreKit, and HealthKit-related services. The app does not contain custom cryptography, end-to-end encrypted messaging, VPN/tunneling, encrypted file storage, or user-managed encryption keys. The build declares `ITSAppUsesNonExemptEncryption` as `false`.

## Reviewer Attachment Recommendation

Do not attach extra encryption documentation by default. Extra docs can slow review if they introduce questions. Attach this note only if App Review asks for more information.

