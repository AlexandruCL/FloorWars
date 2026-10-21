# Week 1 status (Cristea)

Last updated: 2026-10-21. Source of truth for the task list: `cristea/week_1_tasks.md`. This file says where to pick up.

## Done (merged to `main`)

| Task | What | Merged as |
|---|---|---|
| T1 | Bare RN app in `/app`, Android only, lint/test/tsc, debug APK | PR #1 (merge `71c08e7`) |
| T2 | Kotlin `FloorSensors` module, JS permissions, debug panel | PR #2 (merge `ad6e8a3`) |
| T3 | Health foreground service, pressure and step registration, `getStatus()` | PR #3 (merge `bdeff89`) |
| T4 | Sensor logger screen, CSV export through the share sheet | PR #4 (merge `1b83082`) |

Checks were green on the emulator (`floorwars_api36`) for each. Known gaps are listed under "Open" below.

## Committed, not merged (waiting for review)

- **T5, synthetic traces:** commits `715adff` and `aaa6ee8` on `feat/t5-synthetic-traces`. Generator at `tools/synthetic_traces/generate.py`, 24 files in `/fixtures/synthetic/` (not `/traces`), each marked `# synthetic,true`. **Not real data.** T5's real done-when is still open.
- **T6, device doc:** commit `45ae2cb` on `feat/t6-test-devices`. `/docs/devices.md` lists the emulator as "not a test device" and the two phones as pending. Real T6 is still open.

Not pushed. No PRs yet.

## Open

### Needs real phones (not available yet)

- **T3 phone checks:** notification on a real device; `has_barometer` correct on both test phones; service survives 60 s with the screen off. Also decide whether to keep the partial wake lock and the base `FOREGROUND_SERVICE` permission (see PR #3).
- **T4 phone checks:** step rows (the emulator has no step detector); CSV opened in Sheets or Excel; share sheet on a device.
- **T5 real recordings:** at least 20 labelled traces in `/traces`, covering all six labels, on two devices, in a faculty building, with a matching `labels.csv` row per file. No personal data.
- **T6:** exact manufacturer, model, Android version, barometer, battery settings for both phones.
- **Exit check:** the app installs on both phones.

### Blocked on Ionut

- **T7:** generate the TypeScript API client from `/contracts/openapi.yaml` and add the auth stub. Needs Ionut's `openapi.yaml`, reviewed and approved by both. Ionut also has to confirm the shell runs on his machine.

### Decisions still open

- **Week 1 exit check:** the literal wording ("at least 20 labelled traces in the repo") would be met by synthetic data. Decide whether synthetic counts. Current position: it does not count, and week 1 is not closed until real recordings exist.
- **T3 extras:** keep or drop the wake lock and base `FOREGROUND_SERVICE` permission after testing on real phones.
- **T4 dev skip sign-in:** kept until T7 replaces the auth stub. Remove then.

## Next steps

1. Worker finishes T5 synthetic and T6 doc, then I review and open PRs.
2. Get two Android phones. Run the T3 and T4 phone checks, then T5 recordings and T6 device details.
3. Ionut delivers `/contracts/openapi.yaml` for T7.
4. Close week 1 once T5 real data, T6 and T7 are done and the app installs on both phones.

## Test build for a friend's phone (week 1 only)

Goal: a friend records real sensor traces on his phone and sends the CSV back. Chosen route: a **release APK** with the dev skip-sign-in button kept in release builds.

**Still needed in code (not done yet):** the skip button is currently `__DEV__`-only, so release builds cannot reach the sensor logger. Change its gate so it also shows in this release build, behind an explicit flag, and remove it with T7. Needs a Worker task before the build.

Steps once that change is merged:

1. Build: `cd app/android` then `./gradlew assembleRelease`. Output: `app/android/app/build/outputs/apk/release/app-release.apk`. The template signs release with the debug key, which is fine for this test only.
2. Send the APK to the friend directly (chat, Drive, email). Don't commit it or put it on GitHub.
3. Friend: allow installs from this source, install, open the app, tap **Skip sign-in (dev)**, then **Sensor logger** on Home.
4. Friend: grant the permissions, pick a label and placement, tap **Start**, wait about 30 s, tap **Stop and save**, then **Share CSV** and send the file to the owner.
5. Owner: check the CSV header (`# device_model`, `# has_barometer`, `# label`, `# placement`) and that pressure rows exist. Step rows only appear if the friend's phone has a step detector.
6. Record the phone in `docs/devices.md` as a borrowed device, with the exact model string from the CSV header.

Limits of this route:

- A release build can't be pulled with `adb`, so the share sheet is the only way to get the file.
- The friend's phone may kill background services. Check the battery setting on his phone (Unrestricted) before the recording.
- Traces from this route still don't count as T5's two-device set until the owner has both phones.
- Consent: the friend agrees to the recording. The CSV holds no name or location.

## Environment notes

- Emulator: `floorwars_api36` (API 36, `sdk_gphone64_x86_64`). Pressure sensor present (`Goldfish`), no step detector.
- adb is not on PATH: `C:\Users\alexc\AppData\Local\Android\Sdk\platform-tools\adb.exe`.
- `app/android/local.properties` is gitignored; use forward slashes in `sdk.dir`.
- Impeccable plugin: installed for this repo from `alex-skills` (source `ByChokeYT/Impecable`, not upstream). Skills did not load in the Worker session.
