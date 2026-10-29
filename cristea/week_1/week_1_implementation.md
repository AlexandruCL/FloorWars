# Week 1 implementation (Cristea)

For Ionut. This file explains what is in `main` for week 1, how the pieces fit, and how to run the app on the emulator. The project reference is `IMPLEMENTATION_PLAN.md`. The task list is `cristea/week_1_tasks.md`. Open phone work is in `cristea/phone_tests.md`.

## 1. What the app does

FloorWars is a campus territory game. A student logs stair climbs with the phone's barometer and step detector, and the app turns verified climbs into points for their faculty's claim on a building. Week 1 builds the app shell, the sensor logging path and the contract. It does not yet send data to a server.

What works in `main` today:

- The app opens on a Sign in screen. A stub sign-in (or the dev skip button) takes you to Home.
- Home links to the **Sensor logger**.
- The sensor logger records one labelled trace: pick a label and a placement, start, stop, and save a CSV on the phone. The CSV can be shared through the Android share sheet.
- The Kotlin native module logs pressure and step events in a foreground service while recording.
- The API client is generated from the approved contract, and an auth stub stores a dummy token.
- The scoring rule for stair steps and the floor-equivalent display helper exist as pure code with tests.

What does not exist yet: the backend, real auth, uploads, the classifier and segmenter (Week 2), and the claim transaction.

## 2. Repository map

| Path | What it is |
|---|---|
| `IMPLEMENTATION_PLAN.md` | Project reference and six-week plan (source of truth) |
| `README.md` | Project overview, decisions and working rules |
| `app/` | React Native app and the Kotlin native module |
| `contracts/openapi.yaml` | API contract (OpenAPI 3.1), approved |
| `cristea/` | Cristea's week 1 files: tasks, this implementation note, phone tests |
| `docs/trace_format.md` | What a trace file must look like and which values are still to validate |
| `docs/devices.md` | Test device log (both phones and the emulator) |
| `fixtures/synthetic/` | 24 labelled synthetic traces and `labels.csv`. Not real data |
| `tools/synthetic_traces/generate.py` | Seeded generator for the synthetic traces |
| `tools/validate_traces/validate.py` | Checker for trace files, checks 1 to 9 from `docs/trace_format.md` |

## 3. The app

### 3.1 Stack and setup

- React Native 0.88.0, bare workflow, TypeScript, Android only. Versions are pinned exactly in `app/package.json`. `app/.npmrc` sets `save-exact=true`.
- Tooling: ESLint (`@react-native/eslint-config`), Prettier, Jest with React Native Testing Library 14, Husky and lint-staged (pre-commit).
- Navigation: React Navigation. `app/src/navigation/RootNavigator.tsx` has two stacks, `Auth` (Sign in) and `Main` (Home, Sensor logger). `App.tsx` holds `isSignedIn` in state.
- `app/README.md` has the setup commands, checks, run and release instructions.

### 3.2 Screens

- **Sign in** (`app/src/screens/PlaceholderScreens.tsx`): "Sign in (stub)" calls the auth stub. "Skip sign-in (dev)" appears when `DEV_SKIP_SIGN_IN` is true.
- **Home**: a button to the sensor logger.
- **Sensor logger** (`app/src/screens/SensorLoggerScreen.tsx`):
  - Labels: `stairs_up`, `stairs_down`, `elevator_up`, `walk_flat`, `shake`, `blow`.
  - Placements: `pocket`, `hand`, `bag`.
  - **Start recording**: asks for the activity and notification permissions. It refuses without the activity permission and shows an error.
  - A timer counts up while recording. The label and placement lock while recording.
  - **Stop and save**: writes the CSV and shows "Saved <file name>".
  - **Share CSV**: opens the Android share sheet with the file (`react-native-share` 12.3.1, pinned).
- **Debug panel** (`app/src/native/FloorSensorsDebug.tsx`): shown on the Sign in screen in debug builds only (`__DEV__`). It has buttons for start, stop and status.

### 3.3 Flags and the auth stub

- `app/src/config/devFlags.ts`: `DEV_SKIP_SIGN_IN = true`. This makes the skip button show in release builds, so a tester can reach the logger without a debug build. It must be removed or set to false when real auth replaces the stub.
- `app/src/auth/authStub.ts`: `signInWithStub` stores a dummy token in `react-native-keychain` and calls back, which switches the navigator to Main. It never calls a server. `getAccessToken()` reads the token back for the API client.

### 3.4 API client and generated types

- `app/src/api/schema.ts` is generated from `contracts/openapi.yaml` by `openapi-typescript` 7.13.0. Do not edit it by hand. Regenerate with `npm run generate:api` in `app/`. The output is byte-identical when the contract is unchanged.
- `app/src/api/client.ts`: a small typed `fetch` wrapper, `api(method, path, ...)`. It adds the bearer token and throws `ApiError` on non-2xx responses. The base URL is a placeholder (`https://api.example.invalid/v1`).
- `app/__tests__/contract/samples.ts` and `app/__tests__/apiContract.typecheck.test.js`: typed samples of the auth, check-in and segment bodies, checked by the TypeScript compiler from Jest. A wrong field fails `npm test`. There is no CI yet, so this runs locally.
- **TypeScript override:** `openapi-typescript` 7.x declares a peer on TypeScript 5, and the app uses TypeScript 6. `app/package.json` has a scoped `overrides` entry that fixes the install. Remove it when a release accepts TypeScript 6. Details are in `app/README.md`.

### 3.5 Scoring helpers (pure code)

- `app/android/app/src/main/java/com/floorwars/floorsensors/classifier/StepScoring.kt`: `stepsScored(steps, ascentM)` returns `steps` only if steps per metre of ascent is between 4 and 8 and ascent is between 2.0 and 120.0 m (both inclusive). Otherwise it returns 0. Elevator rides, flat walking, shaking and descents score 0. Covered by `StepScoringTest`.
- `app/src/scoring/floorEquivalent.ts`: `floorEquivalent(steps)` = steps / 20, rounded down. It is a display estimate only, always shown as "floors (estimate)". Nothing is stored as a floor.

These thresholds are starting values. They get tuned from real recordings (see `cristea/phone_tests.md`).

### 3.6 Native sensing module (Kotlin)

Package `com.floorwars.floorsensors`, under `app/android/app/src/main/java/com/floorwars/`.

- `FloorSensorsModule.kt`: the JS-facing module. Methods: `startLogging(label)`, `stopLogging()`, `getStatus()` (returns `logging`, `label`, `has_barometer`, `buffered`), `saveTrace(placement)` (writes the last stopped session to CSV and resolves to its path). Emits `onStatusChange { logging, label }`.
- `FloorSensorsService.kt`: a foreground service of type `health`, with a persistent notification on the "Sensor logging" channel ("Logging sensors / Label: …").
  - Registers `TYPE_PRESSURE` and `TYPE_STEP_DETECTOR` at `SENSOR_DELAY_GAME`. A missing sensor is skipped, and `has_barometer` reports the pressure sensor.
  - Holds a partial wake lock while logging, so readings keep arriving with the screen off. Whether this is needed on real phones is an open question (see `cristea/phone_tests.md`).
  - Keeps raw events in `SensorEventBuffer` (in memory, capacity 100,000, drops the oldest when full). The buffer is lost if Android kills the service.
  - Records a `TraceSession` (label, start and stop times) for `saveTrace`.
- `SensorEventBuffer.kt`: the bounded buffer above, pure Kotlin, with a JUnit test.
- `TraceCsv.kt`: writes the CSV. Format below. Pure Kotlin, with a JUnit test.
- `FloorSensorsPackage.kt`, `MainApplication.kt`, `MainActivity.kt`: package wiring. `MainActivity` has the `RNScreensFragmentFactory` override that react-native-screens needs on Android.
- `classifier/StepScoring.kt`, `classifier/Classifier.kt`, `segmenter/Segmenter.kt`: the scoring rule is implemented. `Classifier.kt` and `Segmenter.kt` are empty stubs for Week 2.
- `PureKotlinPackagesTest` fails the build if the segmenter, classifier or scoring packages import Android packages.

Permissions: the JS side asks for `ACTIVITY_RECOGNITION`, `POST_NOTIFICATIONS` and checks `FOREGROUND_SERVICE_HEALTH` (install time). The manifest declares the foreground service permission and the service entry.

### 3.7 CSV format (what the app writes)

```
# device_model,<manufacturer> <model>
# has_barometer,true|false
# label,<label>
# placement,<placement>
# start_utc,<ISO time, ms>
# stop_utc,<ISO time, ms>
sensor,timestamp_ns,elapsed_s,value
pressure,<ns>,<s>,<hPa>
step,<ns>,<s>,1.0
```

Files are saved in the app's private storage at `files/traces/<label>_<placement>_<startUTC>.csv`. The full spec and the checks are in `docs/trace_format.md`.

## 4. Contract

- `contracts/openapi.yaml`: OpenAPI 3.1, `/v1`, 18 paths, approved by both members on 2026-10-21. The building-territory revision (merged after review) replaces the floor endpoints with `GET /buildings/{id}/standings`, renames the segment field to `steps_scored`, and renames the WebSocket event to `building_flipped`.
- Inferred fields (anything the plan does not define) are marked `Inferred:` in their descriptions. Changes after approval go through a reviewed PR.
- Validation: `openapi-spec-validator` reports OK. Redocly reports 14 warnings and no errors (tag descriptions, a license field, a 4xx on the public teams list, and the 101 response on `/ws`).

## 5. Trace data (synthetic)

- `tools/synthetic_traces/generate.py` creates 24 traces with a fixed seed. Output is identical across runs. It writes to `fixtures/synthetic/` and clears old synthetic files first.
- Each synthetic file has `# synthetic,true` and `# device_model,SYNTHETIC`, and is never counted as real.
- `tools/validate_traces/validate.py` checks files against `docs/trace_format.md` section 4 (checks 1 to 9), and prints `PASS` or `FAIL` per file. Synthetic files pass 24 of 24. Check 9 is the pressure-steps match.
- The stairs margin is thin: `stairs_up` synthetic files reach 4.47 steps per metre against the 4.0 bound. Open decision in `cristea/phone_tests.md`.

## 6. Running the app on the emulator

These are the commands used on this machine (Windows, Git Bash). Adjust the paths if your SDK is elsewhere.

### 6.1 One-time setup

1. Install Android Studio, or the Android SDK command-line tools, with platform 36, build-tools, NDK 27 and the emulator.
2. Create an AVD named `floorwars_api36` (API 36, `x86_64`, Pixel 7 profile). It has no Play Store.
3. Set `app/android/local.properties` with `sdk.dir=C\:/Users/<you>/AppData/Local/Android/Sdk`. Forward slashes or escaped colons, because backslashes break `.properties` files. The file is gitignored.
4. Install dependencies in `app/`:
   ```sh
   cd app
   npm install
   ```

### 6.2 Start the emulator

Memory matters: the emulator needs about 2 GB. Close other heavy programs first.

```sh
EMU="/c/Users/alexc/AppData/Local/Android/Sdk/emulator/emulator.exe"
"$EMU" -avd floorwars_api36 -no-snapshot-save -no-boot-anim &
```

Wait until the device has booted:

```sh
ADB="/c/Users/alexc/AppData/Local/Android/Sdk/platform-tools/adb.exe"
until [ "$("$ADB" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; do sleep 5; done
"$ADB" devices
```

Expected: `emulator-5554 device`.

### 6.3 Option A: debug build with Metro (for development)

```sh
cd app
npm start            # Metro, keep this running in its own terminal
```

In a second terminal:

```sh
cd app
npm run android      # builds the debug APK, installs and launches it
```

The debug build loads JavaScript from Metro on port 8081. The emulator reaches it with `adb reverse tcp:8081 tcp:8081`, which `npm run android` sets up.

### 6.4 Option B: release test build (what the friend test uses)

No Metro needed. The JavaScript is bundled into the APK.

```sh
cd app/android
./gradlew assembleRelease
```

Output: `app/android/app/build/outputs/apk/release/app-release.apk`. It's signed with the debug key, so it's for testing only.

Install and launch:

```sh
ADB="/c/Users/alexc/AppData/Local/Android/Sdk/platform-tools/adb.exe"
cd app/android
"$ADB" install -r app/build/outputs/apk/release/app-release.apk
"$ADB" shell am start -n com.floorwars/.MainActivity
```

If you have Metro running from option A, stop it first so you know the release bundle is standalone.

### 6.5 Walk through the app on the emulator

1. The Sign in screen shows. Tap **Skip sign-in (dev)** (or **Sign in (stub)**).
2. On Home, tap **Sensor logger**.
3. Pick a label and a placement. Tap **Start recording**, grant the permissions the first time.
4. Wait about 30 s. The timer counts up and the notification says "Logging sensors".
5. Tap **Stop and save**. The screen shows "Saved <file>.csv".
6. Tap **Share CSV**. The share sheet lists the file. Dismiss it with the back button.

On the emulator the pressure sensor is virtual (`Goldfish`) and returns a constant 1013.25 hPa, and there is no step detector. So the file has pressure rows and no step rows.

### 6.6 Useful commands

```sh
ADB="/c/Users/alexc/AppData/Local/Android/Sdk/platform-tools/adb.exe"
"$ADB" logcat -d -s FloorSensors:I AndroidRuntime:E     # app logs and crashes
"$ADB" shell am force-stop com.floorwars                  # stop the app
"$ADB" uninstall com.floorwars                            # remove it
```

On Git Bash, paths that start with `/sdcard` get rewritten. Set `MSYS_NO_PATHCONV=1` before `adb shell` commands that use device paths. Dump the screen text with:

```sh
MSYS_NO_PATHCONV=1 "$ADB" shell uiautomator dump /sdcard/ui.xml
MSYS_NO_PATHCONV=1 "$ADB" exec-out cat /sdcard/ui.xml | grep -o 'text="[^"]*"' | sort -u
```

A release build is not debuggable, so `adb shell run-as com.floorwars` does not work on it. Get the CSV through the share sheet.

### 6.7 Checks before you commit

From `app/`:

```sh
npm run lint
npm test
npx tsc --noEmit
```

From `app/android/`:

```sh
./gradlew ktlintCheck
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

Each should exit 0. Run `npm install` again after pulling, because a stale `node_modules` can miss new dependencies. That gave a Metro error during the release build on this machine.

## 7. Working rules this week

- One branch per task, one PR into `main`. The other member reviews.
- No co-author trailers on commits.
- Don't commit APKs, keystores, `local.properties`, or real recordings before the privacy decision in `cristea/phone_tests.md`.
- Changes to the approved contract go through review by the other member.

## 8. Known limits

- No real auth. The stub stores a dummy token and never calls a server.
- No upload. The CSV leaves the phone only when shared.
- The buffer is in memory. If Android kills the service mid-recording, that recording is lost.
- Thresholds (4 to 8 steps per metre, 2.0 m minimum ascent, 20 steps per floor-equivalent) are starting values, not measured on real phones.
- No CI. The contract test and the other checks run locally.
- 54 npm vulnerability reports (5 moderate, 49 high) are not triaged.
