# Android Explore performance check

Use this checklist on a physical Android device after installing the same debug or release-candidate build being reviewed. Source inspection and emulator behavior do not establish real-device responsiveness.

## Setup

1. Connect one device and confirm that `adb devices -l` shows exactly one `device` entry.
2. Record the phone model, Android version, build commit, build type, network type, and whether Explore already has saved data.
3. Install the build under review, then open Gaia Eyes once and complete sign-in/onboarding before timing.

From `gaiaeyes-android/`:

```sh
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
SDK_DIR="$(sed -n 's/^sdk.dir=//p' local.properties | head -n 1)"
ADB="$SDK_DIR/platform-tools/adb"
./gradlew :app:assembleDebug
"$ADB" install -r app/build/outputs/apk/debug/app-debug.apk
```

## Measurements

Run each scenario three times and keep every result rather than reporting only the fastest run.

### Cold launch

```sh
"$ADB" shell am force-stop com.gaiaeyes.app
"$ADB" shell am start -W -n com.gaiaeyes.app/.MainActivity
```

Record `ThisTime`, `TotalTime`, and `WaitTime`.

### Warm launch

Send Gaia Eyes to the background, wait five seconds, reopen it from the launcher, and record the same `am start -W` values. Confirm whether cached Home content appears before network refresh completes.

### Explore with saved data

1. Open Explore after it has loaded successfully once.
2. Record the time from tapping Explore until the hub cards are usable.
3. Open and return from All Drivers, Space Weather, Local Conditions, Magnetosphere, and Schumann Resonance.
4. Confirm every destination remains present and tappable while another source is updating or unavailable.

### Refresh and degraded network

1. Refresh Explore on a normal connection and record time until the updating state clears.
2. Repeat after temporarily disabling network access.
3. Confirm saved values are labeled as saved, unavailable sources are explicit, and no card changes position or disappears.
4. Restore network access and confirm a retry updates the affected destination.

### Scroll rendering

Reset frame statistics, scroll the Explore hub and All Drivers list from top to bottom three times, then collect the report:

```sh
"$ADB" shell dumpsys gfxinfo com.gaiaeyes.app reset
# Perform the scroll pass on the device.
"$ADB" shell dumpsys gfxinfo com.gaiaeyes.app framestats > explore-framestats.txt
```

Keep the frame report with the device notes. Compare before/after results from the same device, build type, data state, and network conditions.

## Acceptance record

Record:

- cold and warm launch results for all three runs;
- cached Explore entry time;
- refresh time on normal and degraded networks;
- any visible card movement, blank surface, or input delay;
- frame report path;
- screenshots of the hub, All Drivers, Local Conditions, and one unavailable/saved state.

Do not mark sluggishness fixed until this physical-device pass has repeatable before/after evidence.
