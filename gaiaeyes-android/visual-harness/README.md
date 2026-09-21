# G026 isolated production-form harness

This standalone test project compiles the actual production Kotlin and resources from `../app/src/main`. It renders `MigraineFollowUpForm` and uses the actual `MigraineFollowUpFormController`, accepted store/repository, `GaiaApiClient`, and migraine types. There is no second implementation of the form or its recovery state machine.

The target application ID is `com.gaiaeyes.g026.synthetic`; the instrumentation package is `com.gaiaeyes.g026.synthetic.test`. These are internal, disposable test artifacts. They are not the owner test app or an Android release build.

## Isolation

- `IsolatedApplication` replaces production startup. Neither `GaiaEyesApplication` nor `HomeViewModel` is constructed. Firebase, WorkManager, Health Connect, auth, notifications, and billing startup are not invoked.
- The custom manifests remove all requested permissions, providers, services, receivers and automatic metadata from dependencies. Only the two harness activities remain in the target manifest. Both packaged APKs were checked before installation.
- The application asserts its package, denied INTERNET permission, invalid API base, and empty auth/Firebase/billing configuration. It also enables a main-thread network death policy. OS permission denial applies to all app threads; StrictMode alone is not the network boundary.
- Both `GaiaApiClient` HTTP clients use `SyntheticEngine`. It handles requests in memory, accepts only `example.invalid` and the two exact synthetic routes, and checks the fixed synthetic token. It never opens a listening socket or makes a network request.
- No production `local.properties`, Firebase file or environment credentials are read. The only asset is the accepted synthetic migraine JSON fixture copied from the test resources.
- The runtime uses a fresh AVD and app data, a dedicated ADB server, an explicit emulator serial, airplane mode, and disabled Wi-Fi/mobile data. Never use the historical signed-in Health Connect AVD, a physical device, or an unqualified `adb install`.

## Build with installed dependencies only

From `gaiaeyes-android`:

```sh
env JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' \
    ANDROID_HOME='/Users/gennwu/Library/Android/sdk' \
    ./gradlew -p visual-harness --offline :app:assembleDebug :app:assembleDebugAndroidTest
```

The project reuses existing dependency versions. No SDK/image/library installation is part of this recipe. Built-in Kotlin needs `android.sourceSets.main.kotlin`, per the [Android build documentation](https://developer.android.com/build/migrate-to-built-in-kotlin#source-sets); adding the production Kotlin directory to the Java source set does not compile it with this AGP version.

## Runtime and evidence

The accepted local run used installed Emulator 36.6.11.0, Android 36 ARM64 16 KB Play image, fresh AVD `GaiaG026Synthetic`, 720 × 1280 px at 320 dpi (360 × 640 dp), and application font scales 1.0 and 1.6. Font scaling is scoped to the harness Activity. The device's system font setting was not changed.

Before installing, verify the merged/packaged manifests still have the isolated Application, no requested permissions or startup components, and the intended target/test identities. Start a fresh disposable AVD with its own `ANDROID_AVD_HOME`, `ANDROID_USER_HOME` and `ANDROID_EMULATOR_HOME`. Confirm `adb ... emu avd name` and `ro.kernel.qemu=1`, no prior Gaia packages and zero accounts; disable the disposable device's radios before installing. Use the explicit owned serial for every operation. Do not run `connectedAndroidTest`, which may select unrelated connected devices.

After installing only the synthetic APKs on that verified emulator, the instrumentation command for the original run was:

```sh
/Users/gennwu/Library/Android/sdk/platform-tools/adb -P 5039 -s emulator-5586 shell \
  am instrument -w -r \
  -e class com.gaiaeyes.app.visualharness.ActualFormInteractionTest \
  com.gaiaeyes.g026.synthetic.test/com.gaiaeyes.app.visualharness.IsolatedRunner
```

The original emulator has been stopped and its writable data removed. That command requires recreating a fresh isolated runtime; do not substitute a daily-use device. The exact fresh configuration, boot arguments, installation/readback receipts, screenshots, JSON ledgers, semantics, logs, and cleanup receipt are in:

`/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g026-isolated-form-visuals`

Screenshots and exact-value ledgers are written inside the synthetic app's `files/g026` directory. Export them with explicitly targeted `adb exec-out run-as com.gaiaeyes.g026.synthetic cat files/g026/<name>` before stopping the owned emulator. Only remove directories and stop processes created for this run; do not kill a shared ADB server.

## Coverage and boundaries

Ten distinct actual-form instrumentation cases passed: the nine-case suite and one added focused large-font case. The earlier one-case smoke run duplicates one of those nine. Coverage includes untouched full medicine metadata, duplicate names, exact dose, missing versus zero, add/edit/reorder, native date/time callbacks, unchanged microsecond timestamps, keyboard/scroll, save receipt refresh, initial unavailable load, loaded-unavailable exact retry, uncertainty/conflict GET review without auto-save/merge, explicit close/discard, stale native callbacks, and account replacement during a save.

This verifies the production form/controller seam on an emulator with synthetic services. It does not verify production HomeViewModel construction, the real auth observer, notification navigation, process death/recreation persistence, physical-device behavior, real network/backend responses, Health Connect, Firebase delivery, purchase/restore, or release/store readiness. The draft remains memory-only. The synthetic ledger's mutation count describes only the in-process fixture.

No production source change was needed for this harness. G023 remains the existing owner APK; it does not contain this harness or the later follow-up form work.

## G037 visual/data parity extension

`LocalConditionsParityScreenTest` uses `IsolatedMainAppActivity` with the explicit `g037` intent flag and the actual `GaiaEyesApp`, `HomeViewModel`, account observer, repositories and API client. The original G026 description above about not constructing HomeViewModel applies to the form harness, not this main-app extension. Existing medicine scenarios do not enable the G037 flag.

The added local/Drivers JSON assets are labelled synthetic fixtures, with public-derived weather/forecast values and deliberately populated pollen/AQI inputs. The in-memory server requires synthetic bearer auth for profile/Drivers/dashboard reads and no bearer for the public local route. Both manifests still deny INTERNET and remove automatic startup components. No production service, real account, Health Connect sample, billing flow or Firebase client is exercised.

Five cases cover normal and activity-scoped 1.6 text across Home/Explore/Drivers/Local Conditions, full pressure text layout, native navigation, empty pollen without losing weather/AQI, a failed refresh retaining saved data, an actual API-client 401 and synthetic sign-out, plus the preserved ULF regional/history component. Screenshots/semantics/request ledgers are written to `files/g037`. The screenshot helper waits 350 ms after Compose/Android idle for the system window transition to settle. iOS references render actual production components in an owned fixture copy; they are not authenticated whole-app acceptance.

The G037 delivery packet contains the final results, comparison gallery, build commands, isolated runtime receipts and owner APK guide:
`/Users/gennwu/Documents/Codex/2026-09-05/we/outputs/g037-android-visual-data-parity`
