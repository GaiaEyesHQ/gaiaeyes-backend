# Android Push Production Acceptance

Do not send a notification until the owner approves the controlled delivery step.

## Production prerequisites

- Apply `supabase/migrations/20260812144904_allow_android_push_tokens.sql` to the connected GaiaEyes project and confirm the `app.user_push_tokens_platform_check` constraint accepts `ios` and `android`.
- Configure the Android release build outside Git with `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `FIREBASE_PROJECT_ID`, `FIREBASE_APPLICATION_ID`, `FIREBASE_API_KEY`, and `FIREBASE_GCM_SENDER_ID` from the same Firebase project.
- Configure the `send_push_notifications` GitHub environment with `FCM_PROJECT_ID` and `FCM_SERVICE_ACCOUNT_JSON`; confirm the service account can use Firebase Cloud Messaging HTTP v1 for that same project.
- Run `:app:validateReleaseConfiguration`, `:app:testReleaseUnitTest`, `:app:lintRelease`, and `:app:assembleRelease` with the intended release inputs.

## Samsung acceptance checklist

Use a production-signed build on the Samsung SM-S918U1 over Wi-Fi. Record timestamps in Central and UTC.

1. Uninstall the old test build, install the production candidate, launch it, and confirm the expected package and version.
2. Sign in to the intended acceptance account. Confirm the notification permission prompt appears on Android 13+ and choose **Allow**.
3. Enable Gaia Eyes notifications and one low-risk notification family. Confirm quiet hours and time zone match the device.
4. Read-only database check: confirm one enabled `android` / `prod` token exists for that user, its mixed-case token was preserved exactly, and `last_seen_at` matches the registration time. Do not print the token.
5. Force-stop and reopen the app. Confirm the same token row is refreshed rather than duplicated.
6. Reboot the phone, reopen Gaia Eyes, and confirm notification settings and token registration remain enabled.
7. With explicit owner approval, queue and send one uniquely identified low-risk acceptance notification to only this account/device.
8. Foreground: confirm one notification appears with the expected title/body, icon, channel, sound/vibration behavior, and no duplicate.
9. Background: repeat once with the app backgrounded; tap it and confirm the intended Gaia Eyes destination opens.
10. Terminated: repeat once after swiping the app away; tap it and confirm cold-start deep-link routing works.
11. Quiet hours: use a controlled test window or approved temporary preference change; confirm delivery is suppressed/deferred as designed, then restore the preference.
12. Deny notification permission in Android settings. Confirm the app explains the disabled state, does not crash, and does not claim delivery is active.
13. Re-enable permission, refresh registration, and confirm delivery resumes only after the user-level Gaia Eyes notification switch is enabled.
14. Sign out or disable Gaia Eyes notifications. Confirm the token becomes disabled and queued events for the user are skipped; do not send another message to prove this without approval.
15. Final read-only check: confirm the approved event has the expected terminal status, timestamp, platform, and no raw token or secret in logs.

Acceptance is complete only when schema, release configuration, token registration, foreground/background/terminated delivery, deep links, permission denial, quiet hours, deduplication, and disable/sign-out behavior all pass on the physical Samsung.
