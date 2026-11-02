# Week 2 summary: Cristea's side

Week 2 in the plan: "a user can sign in and check in; the segmenter detects climbs offline on recorded traces." On the app side, all of it is built and tested and sits in four pull requests: #38, #39, #40 and #41. What is left is the review, the merge and one test on a real phone against the server; the steps are in `finish_week_2.md`.

## At a glance

| Item | What was built | PR | Checked by |
|---|---|---|---|
| W2-0 | Baselines before any change: Android 5 test classes, 14 tests; Jest 6 suites, 16 tests | | Both run on main |
| W2-1 | Segmenter: pressure and step events in, climb segments out | #38 | 6 JUnit cases and a mutation check |
| W2-2 | Rules classifier: stairs, elevator or other per segment, shake and blow rejected | #38 | One test per plan 3.3 table row, boundaries on both sides |
| W2-3 | Trace-replay harness, confusion matrix, `docs/evaluation.md`, CI precision gate | #38 | CI green on GitHub; the gate fails when a false STAIRS is forced |
| W2-4 | Real-data gate (21 real traces), one threshold tuned with logged evidence | #38 | `validate.py`, validation log |
| W2-5 | Sign-in by e-mail code, team choice, tokens in the Keystore, token refresh | #39 | 40 Jest tests, emulator click-through |
| W2-6 | Check-in screen: entrance QR scan or one-shot location | #40 | 77 Jest tests, native build, emulator click-through |
| W2-7 | App pointed at `https://api.floorwars.me/v1`, finishing guide, tester guide, README | #41 | Jest; phone test still to run |

With all four branches merged on top of main: ktlint and 30 Android tests pass, Jest passes 77 of 77 on a cold cache, and the generated API client matches the contract.

## 1. Detecting climbs (Kotlin, PR #38)

Everything here is pure Kotlin with no Android imports, so it runs in plain JUnit and, later, inside the phone's sensing service.

### Segmenter (W2-1)

`app/android/app/src/main/java/com/floorwars/floorsensors/segmenter/Segmenter.kt`

- Takes the pressure samples and step events of a recording (the existing `RawSensorEvent` type) and returns a list of `Segment`s, one per climb.
- Smooths pressure with a centred median over 8 seconds. A median keeps the edges of a stair or lift ramp sharp and removes the short bumps a blow causes. 8 s was chosen because shorter windows still let the synthetic blow bumps through as false climbs (5 s gave 2.5 m of false ascent, 8 s gave 0.35 m).
- Converts pressure to height and marks a sample as climbing when height rises at least 0.05 m/s over 4 s. Weather moves about 0.002 m/s, so it never counts.
- Joins climbing runs less than 15 s apart, so the landings between flights stay in one segment, and drops segments under 1 m.
- Counts the steps inside each segment, accepting events up to 0.3 s late and in any order. All windows are in seconds, because the two test phones log pressure at 10 and 25 Hz.
- Each segment carries ascent, duration, vertical speed, steps, steps per metre and the pressure-steps match flag. The flag calls the existing `stepsScored` rule, so the scoring thresholds stay in one place.
- Tests (`SegmenterTest`): flat walk, stairs (with step events delayed and reversed and pressure shuffled), elevator, shake, blow, and 20 minutes of weather drift. Breaking the match rule makes the elevator test fail, which proves the tests guard it.

### Rules classifier (W2-2)

`app/android/app/src/main/java/com/floorwars/floorsensors/classifier/Classifier.kt`

- Gives each segment a class (STAIRS, ELEVATOR or OTHER) and a reason (STAIRS, ELEVATOR, SHAKE, BLOW or NO_MATCH), so a replay can say why a segment was rejected.
- Rules, in order: steps over less than 2 m of ascent is a shake; a rise with no steps under 5 s is a blow; stairs need the pressure-steps match, 0.1 to 0.9 m/s and 5 s to 3 minutes; elevator needs more than 0.5 m/s and under 1 step per metre; anything else is NO_MATCH.
- Points: a segment's steps when it is STAIRS, zero otherwise.
- All thresholds sit in one named block (`ClassifierThresholds`); the steps-per-metre band is reused from `StepScoring.kt`.
- Tests (`ClassifierTest`): every row of the plan 3.3 table with values just inside and just outside each boundary, plus shake and blow.

### Trace-replay harness and CI gate (W2-3)

`app/android/app/src/test/java/com/floorwars/floorsensors/classifier/TraceReplayTest.kt`

- Runs the segmenter and classifier on every CSV in `traces/` (21 real recordings) and `fixtures/synthetic/` (24 generated ones) and prints a confusion matrix per folder, with precision and recall per class and one line per misclassified file.
- Checks that every CSV header matches its row in `labels.csv`. It only reads those folders.
- The CI gate: the test fails when STAIRS precision on the real traces drops below 0.9. Points ride on STAIRS, and with 3 real stairs climbs a single false STAIRS drops precision to 0.75, so any false STAIRS fails the build.
- `TraceCsv.read` was added so the tests and the harness share one CSV reader (`TraceCsv` could only write before).
- `docs/evaluation.md` holds the matrices, the baseline (commit and data folders) and the validation log.

### Real-data gate and tuning (W2-4)

The real set is enough to evaluate: 21 traces, all six labels.

| Label | SM-S918B | SM-G985F | Total |
|---|---|---|---|
| stairs_up | 1 | 2 | 3 |
| stairs_down | 1 | 3 | 4 |
| elevator_up | 2 | 0 | 2 |
| walk_flat | 1 | 5 | 6 |
| shake | 1 | 2 | 3 |
| blow | 1 | 2 | 3 |
| **Total** | **7** | **14** | **21** |

- `python tools/validate_traces/validate.py traces`: 20 PASS, 1 FAIL that was already reviewed and accepted on 2026-10-29. Logged in `docs/trace_format.md`.
- With the plan's starting thresholds, both real elevator rides came out as OTHER: they moved at 0.59 and 0.69 m/s, under the plan's 1.0 m/s. The elevator threshold was lowered to 0.5 m/s, approved on 2026-11-02, and logged with that evidence. The plan's 3.3 table was updated in the same PR.
- Result on the real traces now: every trace lands in its expected class. STAIRS, ELEVATOR and OTHER all have precision and recall 1.00. The set is small (one wrong trace moves a number by 0.33 to 0.5), so this is a smoke test, not a measurement.

## 2. Signing in (W2-5, PR #39)

- Three screens in `app/src/screens/AuthScreens.tsx`: e-mail with the "18 or older" and "terms" switches, the 6-digit code, and team choice. They call `POST /auth/otp`, `POST /auth/verify`, `GET /teams`, `GET /seasons/active` and `POST /seasons/{id}/join` through the generated client.
- `app/src/auth/session.ts` keeps the access and refresh tokens in `react-native-keychain`, backed by the Android Keystore. The auth stub is gone. `device.ts` sends only what the contract's `DeviceInfo` asks for. `errors.ts` turns every failure into a message that says what to do next.
- `app/src/api/client.ts`: on a 401 the client refreshes once, stores the rotated refresh token and retries. Concurrent 401s share one refresh, so a rotated token is never spent twice. A 401 from the refresh itself signs out and clears the Keychain; network errors and server errors keep the session.
- Each screen has a loading and an error state, and the team list has an empty state. Validation errors clear as soon as the user changes the input they are about.
- `app/src/ui/parts.tsx` holds the shared look: warm paper background, one orange accent, system fonts.
- Tests: rotation, reuse leading to sign-out, and the states of each screen.

## 3. Checking in (W2-6, PR #40)

- `app/src/screens/CheckinScreen.tsx`, reached from Home, offers "Scan entrance code" and "Use my location". Camera and location permissions are asked only when the user taps.
- `app/src/checkin/qr.ts` checks the shape of the entrance token (`fwq1.<payload>.<signature>`) and reads its expiry, so an old code shows "expired" without a network call. The server checks the signature.
- `app/src/checkin/state.ts` holds the states (scanning, finding the position, submitting, success, errors) and maps server errors from `Problem.type` to messages, each with a next step. Success reads "Checked in: <building>, N min left".
- `app/src/checkin/deviceLibs.tsx` connects the native libraries: Vision Camera with the barcode scanner for QR codes, and one high-accuracy location fix through the community geolocation library. `deps.ts` lets the tests swap in fakes.
- Libraries added: `react-native-vision-camera` 5.2.4 with `react-native-nitro-modules` 0.37.1 and `react-native-nitro-image` 0.15.2, `react-native-vision-camera-barcode-scanner` 5.2.4, `@react-native-community/geolocation` 3.4.0. Permissions added to the manifest: camera and both location permissions.
- Tests: QR parsing (valid, malformed, expired-looking), every state and error mapping, and the scanner's "Starting camera..." placeholder.

## 4. Server connection and test material (W2-7, PR #41)

- `API_BASE_URL` now points at `https://api.floorwars.me/v1`, the server Ionut deployed.
- `finish_week_2.md`: the manual steps to finish Week 2, with commands.
- `tester_guide.pdf`: two pages for testers on installing, signing in, checking in and reporting back.
- The root README has the Week 2 status and the decisions taken this week.

## CI and tooling

- `.github/workflows/app.yml`, the app's first CI workflow. The `android` job runs ktlint and the Android unit tests, including the trace-replay gate. The `node` job runs lint, typecheck, Jest, and a check that the generated API client matches `contracts/openapi.yaml`. It passed on GitHub on #38.
- Jest's timeout is 30 s: on a cold cache, which CI always has, the first test of a suite spent over 5 s loading React Native.
- `gradlew` is executable in git, so the Linux runners can start it.

## Bugs found while testing, all fixed

- **Scanner crash.** Opening the scanner showed "No Camera device available!". The barcode plugin's ready-made scanner throws while Vision Camera is still listing the cameras. Fixed by building the scanner view from its parts and showing "Starting camera..." until the camera is ready.
- **Errors from the mock became generic.** The client accepted only `application/json`, so the mock answered every error (sent as `application/problem+json`) with a 500 and the user saw "Could not check in". The client now accepts both.
- **Stale consent error.** The "confirm you are 18" message stayed after both switches were turned on. It now clears when the input changes.
- **Lint.** The new Kotlin failed ktlint, which passes on main. Reformatted, and ktlint now runs in CI.

## Emulator click-through

The whole flow was clicked through on an Android emulator against the Prism mock: sign-in, team choice, staying signed in after a restart, check-in by location, each error message (expired code, rejected code, outside the building, permission denied with Open Settings, server down) and the live camera preview. The record is in the #39 and #40 descriptions. Decoding a real printed code was not possible on the emulator; that is part of the phone test.

## Decisions taken this week

Listed with dates in the root README, "Decisions taken", rows dated 2026-11-02: the segmenter settings, the classifier thresholds and the 0.5 m/s elevator change, the CI gate, the app CI, the check-in libraries, token storage and refresh, error mapping from `Problem.type`, the QR expiry check, the server address, and how testers get the app.

## Still open

- Review and merge #38, #39, #40, #41, in that order.
- The phone test against the server: `finish_week_2.md`, steps 4 to 8. This is the plan's Week 2 exit.
- From Ionut: the real building outlines on the server, printed entrance codes, and a contract PR for `accuracy_m`, the error types, response examples and the `/config` elevator example.
- More elevator rides, in another lift and on the SM-G985F, to re-check the 0.5 m/s threshold.
- The release APK has not been built to the end yet; the debug build has.
- To confirm: the barcode scanner plugin, added without a separate approval.

## Commits

| PR | Commits |
|---|---|
| #38 `feat/w2-segmenter` | `33a223e` segmenter, `b034ab1` classifier, `0325e53` harness, CI workflow and evaluation doc, `9e0deca` precision gate and ktlint, `4a16864` evaluation numbers, `d3e4951` elevator 0.5 m/s, `cdb70df` evaluation baseline |
| #39 `feat/w2-auth` | `16acc3d` sign-in, team choice, Keystore tokens, refresh, `d032cfc` Accept header and validation errors |
| #40 `feat/w2-checkin` | `fd808cf` check-in screen and state mapping, `1f9ba38` camera and location libraries, `84bd8c9` scanner crash fix, `4160e6e` handoff removed (plus the #39 commits) |
| #41 `feat/w2-staging` | `2f57429` server address, `b74c8ad` finishing guide, tester guide and README, `4a07048` VM access noted |
