# Phone tests (Cristea)

Last updated: 2026-10-22. Source of truth for the task list: `cristea/week_1_tasks.md`. This file lists the tests that need real phones, how to run them, and what is still open. Week 1 implementation is explained in `cristea/week_1_implementation.md`.

## Summary

All week 1 tasks are implemented in code (T1 to T7), and the test build for a friend's phone is ready. Update 2026-10-29: 21 real traces are in `/traces` with `labels.csv`, from two phones. Checker: 20 PASS, 1 FAIL (check 5, a pause, accepted). The 60 s screen-off run, share sheet and CSV export were checked on the phones and work. Sections below that list this as open are done.

## Tasks

| Task | Status | PR | Notes |
|---|---|---|---|
| T1 Init RN app | Done, merged | #1 (`71c08e7`) | Lint, test, tsc pass. Debug APK installed on emulator |
| T2 Kotlin `FloorSensors` skeleton | Done, merged | #2 (`ad6e8a3`) | ktlint, JUnit, start and stop verified on emulator |
| T3 Foreground service | Done, merged | #3 (`bdeff89`) | Phone checks passed 2026-10-29 (notification, `has_barometer`, 60 s with screen locked) |
| T4 Sensor logger screen | Done, merged | #4 (`1b83082`) | CSV export and share sheet verified on emulator. Step rows, CSV and share sheet verified on both phones 2026-10-29 |
| T5 Labelled traces | Done | #7 | 24 synthetic traces plus 21 real traces in `/traces` with `labels.csv`; checker 20 PASS, 1 reviewed FAIL |
| T6 Test devices doc | Done | #8 | `docs/devices.md` lists both phones |
| T7 TS API client and auth stub | Done. Ionut confirmed the shell starts | #9 | Stacked on the contract (#5) and T8 (#6). Contract test runs under `npm test` (no CI yet) |
| Contract `openapi.yaml` | Approved by both | #5 | Inferred fields marked in the file |
| T8 Release test build | Done | #6 | `DEV_SKIP_SIGN_IN` flag, release APK built, installed and tested on both phones |

Merge order: #5 (contract), #6 (T8), #7 (T5), #8 (T6), #9 (T7).

## Building territory (after week 1)

Decided 2026-10-22, reviewed by Ionut. Source of truth: `IMPLEMENTATION_PLAN.md` sections 2, 3.3, 5, 6.

| Branch | Base | PR | Content |
|---|---|---|---|
| `docs/plan-building-territory` | main | new | Plan changes (territory, stair steps, floor-equivalent, week plan) |
| `feat/building-territory-code` | main | new | Step scoring rule (`StepScoring.kt`) and floor-equivalent helper |
| `feat/building-territory-contract` | `feat/t7-api-client-auth-stub` | new | Contract changes (standings, `steps_scored`, `building_flipped`), regenerated client |

- A building is the claimed object. Points are verified stair steps, and a segment scores only if its steps match its pressure change (stairs 4 to 8 steps per metre of ascent; elevator, flat walking and shaking score nothing).
- Floors are a display estimate: 20 verified steps = 1 floor-equivalent, always shown as "floors (estimate)".
- No building floor data is used anywhere.

## Verification

- Checks passed on the emulator or in Jest, as listed in each PR.
- The release APK (T8) was installed and tested on both phones.
- The T7 keychain flow is covered by Jest with a mock only.
- Trace checker: 24/24 synthetic traces pass (checks 1 to 9).

## Real-phone work (done 2026-10-29, kept as the procedure)

Everything below needs real Android phones with a barometer. Two phones are the target for week 1 exit.

### 1. Install the app on each phone

1. Build the release APK on the owner's machine: `cd app/android` then `./gradlew assembleRelease`. Output: `app/android/app/build/outputs/apk/release/app-release.apk`. Rebuild after the T8 PR is merged, so the APK matches `main`.
2. Send the APK directly (Drive link, Quick Share, or a chat app as a document). Don't commit it or put it on GitHub.
3. On the phone: allow installs from that source, install, and tap **Install anyway** if Play Protect warns. No Metro, laptop or server is needed.
4. Set FloorWars to **Unrestricted** in the battery settings before any recording.

### 2. Run the phone checks (per phone)

Record the results per phone in `docs/devices.md`.

| # | Check | Pass when |
|---|---|---|
| 1 | Install with no Metro running | App opens to Sign in |
| 2 | Tap **Skip sign-in (dev)**, then **Sensor logger** | Logger shows label and placement pickers |
| 3 | Tap **Start** without permissions | Refuses with an error |
| 4 | Grant permissions, tap **Start** | Timer runs, notification says "Logging sensors" |
| 5 | Lock the screen for 60 s during a recording | Recording continues (the file has rows for the whole time) |
| 6 | Tap **Stop and save** | "Saved" message |
| 7 | Tap **Share CSV** | Share sheet opens with the file |
| 8 | Open the CSV in a spreadsheet app | Opens; header matches the phone, label and placement |
| 9 | Pressure rows | Present if `has_barometer` is true, about 50 per second, with timestamps |
| 10 | Step rows | Present if the phone has a step detector, during walking or stairs |
| 11 | Record the phone | Exact `device_model` string, Android version, `has_barometer`, step detector yes/no, battery setting, anything phone-specific |

Also record T3's open decision on the partial wake lock and the base `FOREGROUND_SERVICE` permission: check 5 tells us whether the wake lock is needed on this phone.

### 3. Record real traces

Per phone, at least these labels. Stairs in at least two buildings in total, across the phones.

- `stairs_up` and `stairs_down`: real stair climbs, with the phone in pocket, hand and bag.
- `elevator_up`: rides, to check that the rule rejects them.
- `walk_flat`, `shake`, `blow`: to check the negative cases.

Save each recording as the app exports it. Don't edit the CSV.

### 4. Collect and validate the data

1. Put the CSVs in `fixtures/real_data/` (folder decision below). Don't commit them until the consent and privacy decision below is made.
2. Read each file's header before anything else. Check there are no names or locations.
3. Run the checker:
   ```
   python tools/validate_traces/validate.py fixtures/real_data
   ```
   Expect `PASS REAL` or `FAIL` with check numbers. A failure is data to review, not something to delete.
4. For each FAIL, classify the cause: app bug (sampling, metadata), generator (synthetic model), or spec (the expected value in `docs/trace_format.md`). Fix in that order, and report to the owner before changing app code.
5. Measure the TO VALIDATE rows in `docs/trace_format.md` section 2 (sampling rate, storey height, step rate, noise, lift speed, steps per metre on real stairs). Log each in the validation log (section 7).
6. Check 9 margins on real stairs against 4 to 8 steps per metre. Tune thresholds only with logged evidence, and only in the constants block of the checker and the scoring rule.
7. Update `docs/devices.md` with the exact model strings, and mark the phones as tested.
8. Compare the synthetic generator with the real numbers. Change the generator only if the real numbers differ, and rerun the checker on both sets.

### 5. Week 1 exit (real data)

- The app installs on both phones.
- At least 20 real labelled traces, all six labels, two phones, with a `labels.csv` row per file. Synthetic traces don't count.
- Checks 9 and the T3 and T4 phone checks pass, or the failure is logged and understood.

## Closed 2026-10-29 (was open; kept for the record)

- **T3 phone checks:** notification on a real device; `has_barometer` correct on both phones; service survives 60 s with the screen off.
- **T3 decision:** keep or drop the partial wake lock and the base `FOREGROUND_SERVICE` permission, after the phone checks.
- **T4 phone checks:** step rows; CSV opened in a spreadsheet; share sheet on a device.
- **T5 real recordings:** the data collection in section 3 above.
- **Validate the synthetic traces** against real data: `docs/trace_format.md` section 6.
- **T6 phone details:** exact manufacturer, model, Android version, barometer and battery settings for both phones.
- **T8 device test:** install, skip, logger, 30 s recording, share, CSV contents on a device.
- **Exit check:** the app installs on both phones, and there are 20 real traces.

## Open (decisions)

- **Real data folder:** decided 2026-10-29: `/traces`.
- **Committing real CSVs:** they contain device details and timings. Keep them outside the repo, or commit them? Read each header before committing either way.
- **Dev skip sign-in:** `DEV_SKIP_SIGN_IN` stays on for the friend test build. Remove or set to false when the real auth replaces the stub (later week).
- **TypeScript override:** `openapi-typescript` 7.13.0 uses a scoped override for TypeScript 6. Remove when a release accepts TypeScript 6. Alternative: pin 6.7.6 and change the client types.
- **Contract version:** `info.version` still reads `0.1.0-draft`. The approved status line stays until Ionut's review of the territory revision is marked done.
- **Synthetic stairs margin:** `stairs_up` synthetic files reach 4.47 steps per metre, close to the 4.0 bound, because the generator counts steps over the whole 30 s including the walk-in. Change the generator to count steps over the flights only? Changes the synthetic fixtures.

## Friend test workflow

Status: the release APK (T8) was installed and tested on both phones. Use the steps in "Real-phone work, 1. Install the app" and the check table above.

On the friend's phone, the test flow is:
1. Open FloorWars, tap **Skip sign-in (dev)**, then **Sensor logger** on Home.
2. Pick a label and placement, tap **Start**, grant the permissions, wait about 30 s, tap **Stop and save**.
3. Tap **Share CSV** and send the file to the owner.

Limits:
- A release build can't be pulled with `adb`, so the share sheet is the only way to get the file.
- Traces from this route don't count as the two-phone set until the owner has both phones.
- Consent: the friend agrees to the recording. The CSV holds no name or location.

## Next steps

1. PRs: merge in order #5, #6, #7, #8, #9. Then the three building-territory PRs (plan and code to `main`, contract on top of T7).
2. Rebuild the release APK from `main` after the merges.
3. Get two Android phones. Run the phone checks, record traces, and fill `docs/devices.md`.
4. Validate the data with the checker, log the TO VALIDATE values, and tune thresholds only with logged evidence.
5. Decide the real-data folder and the commit policy for real CSVs.
6. Later week: remove the dev skip button when the real auth lands.

## Environment notes

- Emulator: `floorwars_api36` (API 36, `sdk_gphone64_x86_64`). Pressure sensor present (`Goldfish`), no step detector. Memory is tight on this laptop: boot it alone, after closing other heavy apps.
- adb is not on PATH: `C:\Users\alexc\AppData\Local\Android\Sdk\platform-tools\adb.exe`.
- `app/android/local.properties` is gitignored; use forward slashes in `sdk.dir`.
- Impeccable plugin: installed for this repo from `alex-skills` (source `ByChokeYT/Impecable`, not upstream). Skills did not load in the Worker session.
