# Week 1 status (Cristea)

Last updated: 2026-10-21. Source of truth for the task list: `cristea/week_1_tasks.md`. This file says where things stand.

## Summary

All week 1 tasks are implemented in code (T1 to T7), and the test build for a friend's phone is ready. Week 1 is complete on code and synthetic data. Phone validation and real recordings are deferred to later weeks, by decision.

## Tasks

| Task | Status | PR | Notes |
|---|---|---|---|
| T1 Init RN app | Done, merged | #1 (`71c08e7`) | Lint, test, tsc pass. Debug APK installed on emulator |
| T2 Kotlin `FloorSensors` skeleton | Done, merged | #2 (`ad6e8a3`) | ktlint, JUnit, start and stop verified on emulator |
| T3 Foreground service | Done, merged | #3 (`bdeff89`) | Phone checks pending (see below) |
| T4 Sensor logger screen | Done, merged | #4 (`1b83082`) | CSV export and share sheet verified on emulator. Step rows and phone checks pending |
| T5 Labelled traces | Done on synthetic data | #5 | 24 synthetic traces, generator, checker, trace spec. Real recordings deferred |
| T6 Test devices doc | Done, phone entries pending | #6 | `docs/devices.md` with emulator entry and pending phones |
| T7 TS API client and auth stub | Done | #9 (stacked on #8 and #7) | Ionut ran the shell and confirmed it starts. Contract test runs under `npm test` (no CI yet) |
| Contract `openapi.yaml` | Approved by both | #8 | Inferred fields marked in the file |
| T8 Release test build | Done, device test not run | #7 | `DEV_SKIP_SIGN_IN` flag, release APK built, static checks only |

Only PRs #1 to #4 are merged. The rest are open. Merge order: #8, #7, #5, #6, #9.

## Verification

- All checks pass on the emulator or in Jest, as listed in each PR.
- The release APK (T8) has not run on a device. Emulator was skipped for memory.
- The T7 keychain flow is covered by Jest with a mock only.

## Open (needs real phones, later)

- **T3 phone checks:** notification on a real device; `has_barometer` correct on both test phones; service survives 60 s with the screen off.
- **T3 decision:** keep or drop the partial wake lock and the base `FOREGROUND_SERVICE` permission, after testing on real phones.
- **T4 phone checks:** step rows (the emulator has no step detector); CSV opened in a spreadsheet; share sheet on a device.
- **T5 real recordings:** at least 20 labelled traces in `/traces`, all six labels, two devices, in a faculty building, with a `labels.csv` row per file. No personal data.
- **Validate the synthetic traces** against real phones: `docs/trace_format.md` section 6 (TO VALIDATE rows and the validation log).
- **T6 phone details:** exact manufacturer, model, Android version, barometer, battery settings for both phones.
- **Exit check:** the app installs on both phones, and there are 20 real traces. Synthetic traces do not count.

## Requirement (decided)

- **Runs on any Android phone with a barometer.** The app checks the phone's capabilities (barometer, sampling rate, step detector) and adapts. Phones without a barometer use the landing-scan fallback. Nothing depends on a phone model name.
- **Thresholds are tuned from measured results** across the phones we test. The phone model is not a parameter in the app, the config, or the docs.
- **No building data is required.** Ascent is measured in metres from pressure, which needs no floor heights. Floor counts are an open decision (see "Open (decisions)"), not a requirement of the app.
- **Aim: accurate on every phone.** Not claimed until measured. Accuracy is reported from the measured results, not from a model list.

## Open (decisions)

- **Floor counting (decided: option 2).** The game counts stair steps directly, with no conversion to building floors. Ascent in metres is measured from pressure and shown alongside. Reason: elevators produce no steps, so riding a lift scores nothing. Phones without a step detector can't count stairs, so they get metres only. Needs a plan change (sections 6 and 9).
- **Open risk:** step counting can be gamed by walking or shaking on flat ground. The classifier must require a matching pressure change, so flat walking and shaking don't score as climbs.

- **Dev skip sign-in:** `DEV_SKIP_SIGN_IN` stays on for the friend test build. Remove or set to false when the real auth replaces the stub (later week).
- **TypeScript override:** `openapi-typescript` 7.13.0 uses a scoped override for TypeScript 6. Remove when a release accepts TypeScript 6. Alternative: pin 6.7.6 and change the client types.
- **Contract version:** `info.version` still reads `0.1.0-draft`.

## Friend test workflow

Status: the release APK is built (T8), but has not run on a device and has not been sent.

### 1. Build the APK (owner)

```
cd app/android
./gradlew assembleRelease
```

Output: `app/android/app/build/outputs/apk/release/app-release.apk`. It's signed with the debug key, which is fine for testing only. Don't commit the APK or put it on GitHub.

### 2. Send the APK

Use a Drive link (share with the friend's account or "anyone with the link"), Quick Share if you're in the same room, or a chat app sent as a **document**, not a photo. Gmail caps attachments at 25 MB and the APK is about 66 MB.

### 3. Install on the friend's phone

1. Allow installs from the app they opened the file with (Chrome or Files) when Android asks.
2. Tap the APK, then **Install**. If Play Protect says "unknown developer", tap **Install anyway**.
3. No laptop, Metro or server is needed.

### 4. Record a trace (friend)

1. Open FloorWars and tap **Skip sign-in (dev)**.
2. On Home, tap **Sensor logger**.
3. Pick a label (`stairs_up`, `stairs_down`, `elevator_up`, `walk_flat`, `shake`, `blow`) and a placement (`pocket`, `hand`, `bag`).
4. Tap **Start**. Grant the activity and notification permissions when asked. Start refuses without the activity permission.
5. Do the movement for about 30 seconds. The timer counts up and a notification says "Logging sensors / Label: …".
6. Tap **Stop and save**. The screen shows "Saved <file>".
7. Tap **Share CSV** and send the file to the owner.

### 5. What the owner does with the CSV

1. Open the file and check the header: `# device_model`, `# has_barometer`, `# label`, `# placement`, `# start_utc`, `# stop_utc`, then `sensor,timestamp_ns,elapsed_s,value`.
2. Run the checker on it:
   ```
   python tools/validate_traces/validate.py <file.csv>
   ```
   Expect `PASS REAL` or a `FAIL` line with the check numbers. Failures are data to review, not something to delete.
3. Record the phone's exact model string in `docs/devices.md`, as a borrowed device.
4. Keep the file in a local folder with its label and placement. Don't commit real traces to `main` until the consent and privacy notes are settled.
5. Log the result in the validation log, `docs/trace_format.md` section 7: date, device, what was checked, what was measured, any change.

The app doesn't upload anything yet. The CSV only leaves the phone when the friend shares it.

### 6. What to test on each phone

Run these in order and note the result for each phone.

| # | Check | Pass when |
|---|---|---|
| 1 | Install the release APK with no Metro running | App opens to the Sign in screen |
| 2 | Skip sign-in, open Sensor logger | Logger screen shows the label and placement pickers |
| 3 | Start without permissions | Start refuses with an error |
| 4 | Grant permissions, Start | Timer runs, notification shows "Logging sensors" |
| 5 | Lock the screen for 60 s during a recording | Recording continues (check the timer or the file after stop) |
| 6 | Stop and save | "Saved" message, Share CSV opens the share sheet |
| 7 | Open the CSV | Header metadata matches the phone and the chosen label and placement |
| 8 | Pressure rows | Present if `has_barometer` is true, about 50 per second, with timestamps |
| 9 | Step rows | Present only if the phone has a step detector, during walking or stairs |
| 10 | Battery setting | FloorWars set to Unrestricted before recording |
| 11 | Checker | `PASS REAL` for a walk or stairs trace |
| 12 | Model string | Recorded exactly in `docs/devices.md` |

Phone-specific behaviour (for example, a battery saver that stops background sensing) goes in `docs/devices.md` under "Manufacturer-specific behaviour".

## Test build limits

- The release build can't be pulled with `adb`, so the share sheet is the only way to get the file.
- Traces from this route don't count as T5's two-device set until the owner has both phones.
- Consent: the friend agrees to the recording. The CSV holds no name or location.

## Next steps

1. Merge the open PRs in order: #8, #7, #5, #6, #9.
2. Device test of the release APK (T8), on the emulator once memory allows, or on the friend's phone.
3. Get two Android phones. Run the T3 and T4 phone checks, then the T5 recordings and T6 device details.
4. Validate the synthetic traces against real data and update `docs/trace_format.md`.
5. Later week: remove the dev skip button when the real auth lands.

## Environment notes

- Emulator: `floorwars_api36` (API 36, `sdk_gphone64_x86_64`). Pressure sensor present (`Goldfish`), no step detector. Memory is tight on this laptop: boot it alone, after closing other heavy apps.
- adb is not on PATH: `C:\Users\alexc\AppData\Local\Android\Sdk\platform-tools\adb.exe`.
- `app/android/local.properties` is gitignored; use forward slashes in `sdk.dir`.
- Impeccable plugin: installed for this repo from `alex-skills` (source `ByChokeYT/Impecable`, not upstream). Skills did not load in the Worker session.
