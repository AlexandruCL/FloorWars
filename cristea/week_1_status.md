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

No PR is merged yet except #1 to #4. The PRs are open for review and merge in this order: #8, #7, #5, #6, #9.

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

## Open (decisions)

- **Dev skip sign-in:** `DEV_SKIP_SIGN_IN` stays on for the friend test build. Remove or set to false when the real auth replaces the stub (later week).
- **TypeScript override:** `openapi-typescript` 7.13.0 uses a scoped override for TypeScript 6. Remove when a release accepts TypeScript 6. Alternative: pin 6.7.6 and change the client types.
- **Contract version:** `info.version` still reads `0.1.0-draft`.

## Test build for a friend's phone

Status: the release APK is built (T8). Not yet run on a device, and not sent to anyone.

Route: a release APK with the skip-sign-in button, so the friend can reach the sensor logger without Metro or a debug build.

1. Build: `cd app/android` then `./gradlew assembleRelease`. Output: `app/android/app/build/outputs/apk/release/app-release.apk`. Signed with the debug key, for this test only.
2. Send the APK directly (Drive link, Quick Share, or a chat app as a document). Don't commit it or put it on GitHub.
3. Friend: allow installs from that source, install, open the app, tap **Skip sign-in (dev)**, then **Sensor logger** on Home.
4. Friend: grant permissions, pick a label and placement, tap **Start**, wait about 30 s, tap **Stop and save**, then **Share CSV** and send the file to the owner.
5. Owner: check the CSV header (`# device_model`, `# has_barometer`, `# label`, `# placement`) and that pressure rows exist. Step rows only appear if the phone has a step detector.
6. Record the phone in `docs/devices.md` as a borrowed device, with the exact model string from the CSV header.

Limits:

- A release build can't be pulled with `adb`, so the share sheet is the only way to get the file.
- The friend's phone may kill background services. Set the app to Unrestricted in battery settings before recording.
- Traces from this route don't count as T5's two-device set until the owner has both phones.
- Consent: the friend agrees to the recording. The CSV holds no name or location.

## Next steps

1. Merge the open PRs in order: #8, #7, #5, #6, #9.
2. Device test of the release APK (T8), on the emulator once memory allows, or the friend's phone.
3. Get two Android phones. Run the T3 and T4 phone checks, then the T5 recordings and T6 device details.
4. Validate the synthetic traces against real data and update `docs/trace_format.md`.
5. Later week: remove the dev skip button when the real auth lands.

## Environment notes

- Emulator: `floorwars_api36` (API 36, `sdk_gphone64_x86_64`). Pressure sensor present (`Goldfish`), no step detector. Memory is tight on this laptop: boot it alone, after closing other heavy apps.
- adb is not on PATH: `C:\Users\alexc\AppData\Local\Android\Sdk\platform-tools\adb.exe`.
- `app/android/local.properties` is gitignored; use forward slashes in `sdk.dir`.
- Impeccable plugin: installed for this repo from `alex-skills` (source `ByChokeYT/Impecable`, not upstream). Skills did not load in the Worker session.
