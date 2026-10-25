# Week 1 tasks: Cristea (Sensing and Mobile Core)

Source: `IMPLEMENTATION_PLAN.md` sections 4, 9 and 10 (Week 1, Cristea). Week 1 goal: both sides can build and run; contract frozen; first sensor traces recorded.

Rules for every task:

- One branch per task, PR into `main`. Ionut reviews. CI green before merge.
- Do not start a task before its dependencies are merged.
- If a task adds an endpoint, table, env var or threshold, update `IMPLEMENTATION_PLAN.md` or `/contracts` in the same PR.
- Pin the React Native version in T1 and do not upgrade it during the project.
- No Expo Go. Development build only.

## Checklist

Updated after each Worker report. A box is ticked only when the report shows the done criteria passed.

- [x] T1. Init React Native app (merged to `main` via PR #1, merge commit 71c08e7; lint, test, tsc pass; debug APK built and installed on emulator)
- [x] T2. Kotlin `FloorSensors` module skeleton (branch `feat/t2-floorsensors-skeleton`, 6 commits; ktlint, JUnit, lint, test, tsc, assembleDebug pass; permissions and start/stop verified on emulator)
- [x] T3. Foreground service with sensor registration (branch `feat/t3-foreground-service`, 3 commits; emulator checks pass; phone checks deferred until real phones are available)
- [x] T4. Sensor logger screen (merged to `main` via PR #4; emulator checks pass; step rows and phone checks deferred until real phones are available)
- [x] T5. Record labelled traces and commit them (PR #7; synthetic traces in `fixtures/synthetic/` with checker and trace spec. Real recordings and validation of the synthetic data are still to do; see `docs/trace_format.md` section 6)
- [x] T6. Document test devices (PR #8; `docs/devices.md` with the emulator and pending phone entries. Real phone details still to fill in)
- [x] T7. Generate TS API client and auth stub (PR #9, stacked on #5 contract and #6 T8; Ionut ran the shell and confirmed it starts; contract test runs under `npm test`, no CI yet)

Open for later, not blocking week 1 on synthetic data: validate the synthetic traces against real phones (`docs/trace_format.md` section 6), fill in the two phone entries in `docs/devices.md`, and replace the synthetic fixtures with real recordings for T5.

---

## T1. Init React Native app (TypeScript, bare)

**Owner:** Cristea
**Depends on:** nothing
**Plan ref:** 4.1, 4.2, 9.1 (`/app`), 10 (Cristea, first bullet)

**Scope**
- Create the bare React Native app with TypeScript in `/app`, Android target only.
- Pin the React Native version in `package.json` (exact version, no `^`).
- Add navigation shell with two stacks: `Auth` and `Main`. Placeholder screens only.
- Add React Navigation.
- Add ESLint, Prettier, Jest, and pre-commit hooks (for example Husky plus lint-staged).
- Add one passing Jest test for the navigation shell.

**Out of scope**
- API client, auth logic, Kotlin code, sensor code.

**Done when**
- `npm install`, `npm run lint`, `npm test`, `npx tsc --noEmit` all pass.
- The app builds and installs as a debug APK on at least one Android phone or emulator.
- README in `/app` lists the exact setup commands.

---

## T2. Kotlin module `FloorSensors` skeleton

**Owner:** Cristea
**Depends on:** T1 merged (so the native module is wired into the RN app)
**Plan ref:** 4.3, 10 (Cristea, second bullet)

**Scope**
- Create the native module under `/app/android`, package `FloorSensors`.
- Expose to JS: `startLogging(label)`, `stopLogging()`.
- Event emitter to JS (a no-op event is enough for now).
- Permission requests for `ACTIVITY_RECOGNITION`, notifications, and `FOREGROUND_SERVICE_HEALTH` (declare it in the manifest).
- The segmenter and classifier packages must have no Android imports (keep them pure Kotlin, even though they are empty for now).

**Done when**
- A JS test or a debug button calls `startLogging("test")` and `stopLogging()` without a crash.
- Permission prompts appear and their results are returned to JS.
- ktlint passes.
- JUnit test target exists and runs (one trivial test is enough).

---

## T3. Foreground service with sensor registration

**Owner:** Cristea
**Depends on:** T2 merged
**Plan ref:** 4.1 (native sensing), 4.3, 10 (Cristea, third bullet)

**Scope**
- Foreground service of type `health` with a persistent notification.
- Register `TYPE_PRESSURE` and `TYPE_STEP_DETECTOR` via `SensorManager` when `startLogging` runs. Unregister on `stopLogging`.
- Log raw sensor events to a memory buffer for now (persistence comes in Week 3).
- Report `has_barometer` (true or false) to JS through `getStatus()`.

**Done when**
- On a real phone, the notification shows while logging runs and disappears on stop.
- `getStatus()` returns `has_barometer` correctly on both test phones.
- The service keeps running with the screen off for 60 seconds (manual check, note the result in the PR).

---

## T4. Sensor logger screen

**Owner:** Cristea
**Depends on:** T3 merged
**Plan ref:** 10 (Cristea, fourth bullet)

**Scope**
- Screen with a label picker. Labels: `stairs_up`, `stairs_down`, `elevator_up`, `walk_flat`, `shake`, `blow`.
- Placement picker: `pocket`, `hand`, `bag`.
- Start and stop buttons. A timer while recording.
- On stop, save the trace as CSV (one file per trace) with a header or sidecar containing device model, `has_barometer`, and start and stop timestamps.
- Export through the Android share sheet (`react-native-share`).

**Done when**
- A 30-second recording produces a CSV that opens in a spreadsheet and has pressure and step rows with timestamps.
- The export appears in the share sheet.
- Both labels and placement appear in the file.

---

## T5. Record labelled traces and commit them

**Owner:** Cristea
**Depends on:** T4 merged
**Plan ref:** 10 (Cristea, fifth bullet), 9.1 (`/traces`)

**Scope**
- Record at least 20 labelled traces in a faculty building on 2 devices. Cover at least `stairs_up`, `stairs_down`, `elevator_up`, `walk_flat`, `shake`, `blow`.
- Put the files in `/traces`.
- Write `/traces/labels.csv` with one row per file: file name, label, placement, device, storeys (optional estimate, see docs/trace_format.md), notes.

**Done when**
- At least 20 files in `/traces` with a matching row in `labels.csv`.
- Both test devices are represented.
- Files contain no personal data (no names, no location, no faces).

---

## T6. Document test devices

**Owner:** Cristea
**Depends on:** T5 (needs the two devices used for traces)
**Plan ref:** 10 (Cristea, last bullet), 9 (test devices)

**Scope**
- Write `/docs/devices.md`: exact manufacturer, model, Android version, barometer yes or no, battery-optimisation setting, and any manufacturer-specific behaviour seen during recording.

**Done when**
- Both devices are listed with exact model strings.
- The file is merged into `main`.

---

## T7. Generate TS API client and auth stub (blocked)

**Owner:** Cristea
**Depends on:** `/contracts/openapi.yaml` merged and approved by both (Ionut, Week 1 first 2 days)
**Plan ref:** 4.2 (`openapi-typescript`), 9.2, 9.3, 10 (Cristea, first bullet)

**Scope**
- Generate the TypeScript client from `/contracts/openapi.yaml` with `openapi-typescript`.
- Add an auth stub: a function that stores a dummy token in `react-native-keychain` and switches the navigator from `Auth` to `Main`.
- Write a short hand-over note in `/app/README.md` for Ionut: how to run the shell, how to call the client.

**Done when**
- Ionut runs the shell on their own machine and confirms it starts.
- CI contract test passes against the generated client types.

---

## Week 1 exit check (Cristea share)

Plan exit: the app installs on both phones, and there are at least 20 labelled traces in the repo. T1 to T6 cover that. T7 is Cristea's hand-over to Ionut and waits on Ionut's `openapi.yaml` (plan 9.3, first row).
