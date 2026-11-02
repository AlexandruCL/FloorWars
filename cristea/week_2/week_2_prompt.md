# Prompt: Cristea's Week 2 implementation (FloorWars)

You are implementing Cristea's part of Week 2 in `D:\FloorWars`. Work in one session, on a feature branch from `main`. Follow the checklist in section 3 in order, except where a step says it can run in parallel. Tick each box only after its verification command has run and passed.

## 0. Ground rules

- **Read only the docs in section 2.** Do not read the rest of `IMPLEMENTATION_PLAN.md`, Ionut's `/server` source code, or the Week 3 to 6 plan. The server is described by the contract and `server/README.md`; that is enough. If you need something outside the list, say which file and why before opening it.
- Codebase questions: `graphify-out/` exists, so run `graphify query "<question>" --budget 1500` (or `graphify path`, `graphify explain`) before reading files. Read files only for the lines you need.
- Contract first. Do not edit `contracts/openapi.yaml`. Contract changes are PRs reviewed by Ionut. If the contract blocks you, write the question under "Blocked" in section 4 and go on with other items.
- Do not edit `app/src/api/schema.ts` by hand. Regenerate it with `npm run generate:api` in `app/`.
- Do not install a new dependency without Cristea's approval. Dev tooling already named in this prompt (Prism through `npx`) is fine. Name the candidates, their licence and last release date, and wait for the answer.
- Do not commit real sensor recordings. Read the header of each CSV before any commit (`docs/trace_format.md`).
- Branches: `feat/w2-segmenter` for section W2-1 to W2-4 (including the replay workflow of W2-3), `feat/w2-auth` for W2-5 (including the app CI workflow of W2-7), `feat/w2-checkin` for W2-6. One PR per branch into `main`. Do not run `git checkout` on `main` in a way that loses uncommitted work.
- **The staging VM is not running** (checked 2026-11-02). Build and test everything against the Prism mock (`npm run mock:api` at the repo root, port 4010). Docker and PostGIS are not needed for any item here. The switch to the real server and the phone checks are the last step (W2-7), when the VM is up.
- Before you claim any item done, run its verification command and paste the summary line into your report. No claim without output.
- If a root cause is unclear for a failing test, find the cause first, then fix. Do not patch around a symptom.

## 1. Current state (checked 2026-11-02)

- Week 1 is validated and complete (2026-10-29). `traces/` holds 21 real, committed CSVs with `labels.csv`: all six labels, placements hand, pocket and bag, phones SM-S918B (about 25 Hz pressure) and SM-G985F (10 Hz pressure, step events up to 240 ms behind pressure). Real stairs give 4.3 to 8.7 steps per metre (pocket highest), so the stairs band is 4 to 10. Elevator traces exist only for the SM-S918B. Do not assume a pressure rate or a strict event order: size smoothing windows in seconds, not samples, and tolerate out-of-order step events.
- **Ionut's Week 2 backend is merged into `main`** (PRs #28 to #37) and was deployed and checked with `tools/e2e/e2e_check.py`, but **the VM is stopped now**, so `https://api.floorwars.me` does not answer. The contract is **0.4.1-draft**. It differs from the one the Week 1 shell was generated from:
  - `POST /auth/verify` takes `email`, `code`, `device` (`id` uuid generated once per install, `model`, `has_barometer`) and, for a new account, `accept_terms` and `confirm_adult` (both must be true, else 403).
  - `GET /seasons/active` gives the season id needed by `POST /seasons/{id}/join` (404 when none is active).
  - `POST /auth/otp` answers 202 with no body, 403 for a domain not on the allow-list (`student.upt.ro` by default), 429, 503.
  - `POST /auth/refresh` answers 401 for unknown, expired or reused tokens, plus 429 and 503. A rotated token presented again within a short grace window counts as a retry (401, family kept); later it revokes the family. The client cannot tell the two apart, so any 401 on refresh means sign out.
  - `Checkin` returns `building_id`, `valid_from`, `valid_until` and no building name. Get the name from `GET /buildings`. "N min left" comes from `valid_until` minus now.
  - Check-in 403 problems carry a `type` of `urn:floorwars:problem:<slug>`: `qr-malformed`, `qr-invalid`, `qr-expired`, `qr-not-yet-valid`, `building-unknown`, `location-inaccurate`, `outside-geofence`. `qr-unavailable` is a 503. See `server/README.md`, section "Check-in".
  - A QR token looks like `fwq1.<payload>.<signature>`. The app never verifies it. A new check-in ends the user's previous one.
- `app/src/api/schema.ts` was generated from an older contract. Regenerate it first (`npm run generate:api` in `app/`); expect a diff, and fix the callers.
- `app/android/.../segmenter/Segmenter.kt` and `classifier/Classifier.kt` are 4-line stubs. `classifier/StepScoring.kt` already has the steps-per-metre scoring rule and its thresholds. Do not duplicate it.
- `TraceCsv.kt` and `SensorEventBuffer.kt` already hold the sample and event types. Reuse them. Do not invent parallel types.
- Auth is a stub: `app/src/auth/authStub.ts` (Keychain, dummy token) and `DEV_SKIP_SIGN_IN` in `app/src/config/devFlags.ts`. `app/src/api/client.ts` and `schema.ts` exist. Sign-in and check-in screens are placeholders in `app/src/screens/PlaceholderScreens.tsx`.
- CI: only `.github/workflows/server.yml` exists. There is no workflow for the app or for the trace replay. W2-3 and W2-7 add them.
- Trace folders: real traces in `traces/` (with `labels.csv`), synthetic in `fixtures/synthetic/`. Do not move files.
- `docs/evaluation.md` does not exist yet. You create it in W2-3.

## 2. Documents to read (and only these)

| Doc | Which part | Needed for |
|---|---|---|
| `IMPLEMENTATION_PLAN.md` | Section 10, "Week 2" (Cristea and exit lines only) | All |
| `IMPLEMENTATION_PLAN.md` | Section 3.3, "Sensor fusion" | W2-1, W2-2 |
| `IMPLEMENTATION_PLAN.md` | Section 7.9 (auth pattern) and section 8 (data minimisation, input validation) | W2-5, W2-6 |
| `IMPLEMENTATION_PLAN.md` | Section 11 (evaluation), first row group only | W2-3 |
| `IMPLEMENTATION_PLAN.md` | Section 9.2 (working rules) and 9.3 (Week 2 integration row) | W2-7 |
| `server/README.md` | Sections "Auth" and "Check-in" (behaviour, limits, problem types) | W2-5, W2-6 |
| `tools/e2e/README.md`, `tools/e2e/e2e_check.py` | Whole files. The reference for the order of the calls | W2-5, W2-6, W2-7 |
| `tools/qr/README.md` | Token format and how to make a test QR | W2-6, W2-7 |
| `contracts/prism/README.md` | Whole file (how to run the mock) | W2-5, W2-6 |
| `.github/workflows/server.yml` | Whole file (style of the existing workflow) | W2-3, W2-7 |
| `docs/trace_format.md` | Sections 1, 3, 4 (checks), 7 (validation log) | W2-1 to W2-4 |
| `fixtures/synthetic/README.md` | Whole file (short) | W2-3 |
| `tools/validate_traces/validate.py` | Constants block and check 9 only | W2-2 |
| `contracts/openapi.yaml` | Paths `/auth/otp`, `/auth/verify`, `/auth/refresh`, `/teams`, `/seasons/active`, `/seasons/{id}/join`, `/checkins`, `/buildings`, and the schemas they reference (`OtpVerifyRequest`, `DeviceInfo`, `TokenPair`, `CheckinRequest`, `Checkin`, `Building`, `Problem`) | W2-5, W2-6 |
| Code | `TraceCsv.kt`, `SensorEventBuffer.kt`, `classifier/StepScoring.kt` and its test, `app/src/auth/authStub.ts`, `app/src/api/client.ts`, `app/src/navigation/RootNavigator.tsx` | Matching files |

Do not read `cristea/week_1/week_1_implementation.md` in full. Read `cristea/week_1/phone_tests.md` only if you need the phone test list for W2-7.

## 3. Checklist

Dependencies: W2-0 first. Then two tracks in parallel: **Track A** (W2-1 → W2-2 → W2-3) and **Track B** (W2-5 → W2-6). W2-4 runs with Track A. W2-7 last.

### 3.1 Subagents and worktrees

The work is delegated to project subagents in `.claude/agents/`. Each one owns the checklist items below. This session coordinates: it starts the agents with the Agent tool, routes their blockers, runs the checks, and does W2-7. It does not implement the delegated items itself.

| Agent | Items | Worktree | Model, effort |
|---|---|---|---|
| `w2-preflight` | W2-0 | main checkout (creates the others) | haiku, low |
| `w2-segmenter` | W2-1 | `D:/FloorWars-w2/segmenter` | opus, high |
| `w2-classifier` | W2-2 | `D:/FloorWars-w2/segmenter` (same branch, after W2-1 is committed) | opus, high |
| `w2-replay-harness` | W2-3, W2-4 | `D:/FloorWars-w2/segmenter` (after W2-2 is committed) | opus, high |
| `w2-auth-ui` | W2-5 | `D:/FloorWars-w2/auth-ui` | sonnet, medium |
| `w2-checkin-ui` | W2-6 | `D:/FloorWars-w2/checkin-ui` | sonnet, medium |

Order:

1. Start `w2-preflight` first. Wait for its report.
2. Track A and Track B run in parallel, each in its own worktree. Track A runs `w2-segmenter`, then `w2-classifier`, then `w2-replay-harness`, one after another in the segmenter worktree. `w2-auth-ui` runs alongside.
3. `w2-checkin-ui` starts after W2-5 is committed on `feat/w2-auth`, or earlier if Cristea agrees to branch from `feat/w2-auth`.
4. W2-7 is done in this session, after all agents report.

Rules for this session:

- Start each agent with the Agent tool. Give it the item IDs and its worktree path in the prompt. Its own `.claude/agents/<name>.md` holds its scope, documents and rules.
- Re-run each item's verify command yourself before you tick its box. Agent reports are evidence, not proof.
- If an agent lists a Blocked item, copy it to section 4 and carry on with the other items.
- Worktrees need the project skills copied in, because `.claude/` is gitignored. `w2-preflight` does this. Install the impeccable skills in `D:\FloorWars\.claude\skills` before W2-0 runs, or the copy will miss them.
- UI items (W2-5, W2-6) must use the impeccable skills. Their agent files require it, and a UI agent that cannot load them stops the screen work and reports.
- If the Agent tool does not list these agents, restart the session. Project agents load when a session starts.
- Section 2 applies to the agents too. They read only the documents their agent file names.

Commands for `w2-preflight` to run (also the reference for the paths):

```
git worktree add D:/FloorWars-w2/segmenter -b feat/w2-segmenter main
git worktree add D:/FloorWars-w2/auth-ui -b feat/w2-auth main
# later, when W2-5 is committed (or Cristea agrees to branch from feat/w2-auth):
git worktree add D:/FloorWars-w2/checkin-ui -b feat/w2-checkin feat/w2-auth
mkdir -p <worktree>/.claude && cp -r D:/FloorWars/.claude/skills <worktree>/.claude/
```

Do not run `git checkout` in `D:\FloorWars`. Check `git worktree list` after each addition.

### W2-0 Preflight (first)

*Delegate: `w2-preflight`.*

- [ ] Run `git status` and `git branch --show-current`. Confirm `main` is up to date with `origin/main` (Ionut's backend is in it).
- [ ] Create the worktrees and branches `feat/w2-segmenter` and `feat/w2-auth` from `main`, and copy `.claude/skills` into each (commands in section 3.1). Create `feat/w2-checkin` later, as section 3.1 says.
- [ ] Baseline run, before any change, and record the summary lines:
  - `cd app/android && ./gradlew test`
  - `cd app && npm run lint && npm run typecheck && npm test`
- Done when: both baselines are recorded in the first report. Any failure is listed as pre-existing, not fixed silently.

### W2-1 Segmenter v1 (Track A, Kotlin, pure, no Android imports)

*Delegate: `w2-segmenter` (worktree `D:/FloorWars-w2/segmenter`).*

- [ ] Package `com.floorwars.floorsensors.segmenter`. Keep it free of Android imports.
- [ ] Smoothing on pressure: median or low-pass. Pick one, state the window in the code comment, and keep it a constant.
- [ ] Ascent-window detection over seconds to minutes (no building-wide weather drift).
- [ ] Output type. Use this shape unless you have a reason to change it, and list any change in the report:

  ```kotlin
  data class Segment(
      val startNanos: Long,
      val endNanos: Long,
      val ascentM: Double,        // ascent_m
      val durationS: Double,      // duration
      val vertSpeedMps: Double,   // vert_speed_mps
      val steps: Int,
      val stepsPerM: Double,      // steps_per_m
      val pressureStepsMatch: Boolean,
  )

  class Segmenter {
      fun segment(pressure: List<PressureSample>, steps: List<StepEvent>): List<Segment>
  }
  ```

- [ ] `pressureStepsMatch` is true only when the steps and the ascent agree (use `stepsScored` from `StepScoring.kt`, do not copy its logic).
- [ ] JUnit tests: one flat walk (no ascent), one stair climb, one elevator ramp, one shake (steps, no ascent), one blow (pressure spike, no steps). Use files from `fixtures/synthetic/` or small in-test data. Use `TraceCsv` to read the fixtures.
- Verify: `cd app/android && ./gradlew test`. Paste the summary line.
- Done when: all five cases behave as the plan says, and the tests fail if the match rule is broken (check this by breaking it once and reverting).

### W2-2 Rules classifier v1 (Track A, Kotlin)

*Delegate: `w2-classifier` (same worktree as W2-1, after W2-1 is committed).*

- [ ] `Classifier.kt`: output `stairs`, `elevator`, or `other` per segment, using the starting thresholds in plan section 3.3 (vertical speed, steps per metre, window length, points only when both features match).
- [ ] Reject shake and blow patterns explicitly (shake: steps with no ascent; blow: ascent spike with no steps). Name the constants; do not hard-code numbers inline.
- [ ] Tests for each row of the 3.3 table, including the boundary values.
- Verify: `cd app/android && ./gradlew test`. Paste the summary line.
- Done when: every row of the thresholds table has a test, and the tests pass.

### W2-3 Trace-replay harness and evaluation doc (Track A, Kotlin and docs)

*Delegate: `w2-replay-harness` (same worktree, after W2-2 is committed). It also runs W2-4.*

- [ ] JUnit harness that runs the segmenter and classifier on every CSV in `fixtures/synthetic/` (and `traces/` if it has files). Read the label and placement from the CSV header and `labels.csv`.
- [ ] Print a confusion matrix (counts per label and per predicted class) and the file count. The harness never writes to `fixtures/`.
- [ ] Create `docs/evaluation.md` with three sections: "Confusion matrix", "Baseline", "Validation log". Baseline states that numbers come from synthetic data unless the real set is present. Synthetic numbers are not evaluation (`fixtures/synthetic/README.md`).
- [ ] Record the commit SHA and the data folder used in the Baseline section.
- [ ] Set the precision threshold the plan asks for (section 10, Week 2) as one named constant or config value, and write the baseline number it is based on in `docs/evaluation.md`. Choose a threshold below the baseline so the gate is not flaky, and say so.
- [ ] Add `.github/workflows/replay.yml`: on pull requests that touch `app/android/**`, `traces/**`, `fixtures/**` or the workflow itself, run the harness (`./gradlew test`, JDK 17, ubuntu) and fail when precision is under the threshold. Follow the style of `server.yml`. CI never writes to `fixtures/`.
- Verify: `cd app/android && ./gradlew test`, and paste the confusion matrix. Check the workflow file by reading it against `server.yml`; it runs for real only on the PR.
- Done when: the matrix prints, the doc has the three sections, the threshold and the workflow exist, and Cristea has the numbers to review.

### W2-4 Real-data gate (runs in Track A, blocked on Cristea)

*Delegate: `w2-replay-harness`, as the last step of its run.*

- [ ] Check `traces/` and `labels.csv`. Count the traces per label and per phone.
- [ ] If there are fewer than 20 real labelled traces, or any label is missing, write that in the Baseline section and under "Blocked" in section 4. Do not tune thresholds on synthetic data alone.
- [ ] If real traces exist: run `python tools/validate_traces/validate.py traces` and log the result in the validation log of `docs/trace_format.md` section 7. Tune a threshold only with logged evidence, and only in the constants block.
- Done when: the gate status is written down, with the counts.

### W2-5 Auth screens, token storage, refresh (Track B, React Native)

*Delegate: `w2-auth-ui` (worktree `D:/FloorWars-w2/auth-ui`).*

- [ ] First regenerate the client: `npm run generate:api` in `app/`. The new `schema.ts` (contract 0.4.1-draft) is expected to differ. Fix the callers and commit it with the code that needs it.
- [ ] Base URL: one setting in `app/src/config/` with three values, `mock` (`http://10.0.2.2:4010` for the emulator, the PC's LAN address for a phone), `staging` and `production` (`https://api.floorwars.me`). The default for now is `mock`. Switching is one line, so W2-7 is not a code change.
- [ ] Screens: e-mail entry, OTP entry (6 digits), team choice. Calls through the generated client: `POST /auth/otp`, `POST /auth/verify`, `GET /teams`, `GET /seasons/active`, `POST /seasons/{id}/join`.
- [ ] Sign-in details from the contract: generate the device uuid once and keep it for the install (no new dependency without approval). Send `model` (manufacturer and model) and `has_barometer` (from `FloorSensors.getStatus()`). Show two checkboxes on the OTP step, terms and "I am 18 or older", and send them as `accept_terms` and `confirm_adult`. They are required for a new account, and the app cannot know in advance whether the account is new.
- [ ] Replace the stub in `authStub.ts` with the real flow. Keep the access token and refresh token in `react-native-keychain` (Android Keystore). Keep `DEV_SKIP_SIGN_IN` as it is for the friend build.
- [ ] Refresh interceptor: on 401, call `POST /auth/refresh`, store the new refresh token (rotation), retry the request once. **Single flight:** if several requests get 401 together, only one refresh call goes out and the others wait for its result. Two parallel refreshes with the same token look like reuse to the server. Any 401 from `/auth/refresh` signs the user out and clears the Keychain entry. If the stored refresh token is missing or unreadable at start, sign out; never loop.
- [ ] Each screen has loading, empty, and error states. Errors say what the user can do next. Map: 403 on `/auth/otp` (use a university address; take the allowed domain from the server message, do not hard-code it), 429 (wait and retry, show `Retry-After` if present), 503 (try again later), 401 on `/auth/verify` (wrong or expired code, ask for a new one), 403 on `/auth/verify` (confirm the terms and age), 409 on join (already in a team, show it), 404 on the active season (no season is running).
- [ ] Jest tests: refresh rotation, concurrent 401s sharing one refresh call, 401 on refresh leading to sign-out, and the states of each screen. Use `react-native-testing` patterns.
- [ ] Generated-client check: `npm run generate:api`, then `git diff --exit-code app/src/api/schema.ts` must pass once the regenerated file is committed.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`, and `npm run generate:api`. Paste the summary lines.
- Done when: all Jest tests pass, and the flow works against the Prism mock (`npm run mock:api`; say whether you used `--dynamic` and how the emulator or phone reached it). The mock accepts any code, so the 401, 403 and 429 states are covered by the Jest tests, not by the mock.

### W2-6 Check-in screen: QR and geolocation (Track B, React Native)

*Delegate: `w2-checkin-ui` (worktree `D:/FloorWars-w2/checkin-ui`), after W2-5 per section 3.1.*

- [ ] Screen reached from the main navigator.
- [ ] QR parse: the scanned payload is the token string `fwq1.<payload>.<signature>`. Check only its shape (prefix `fwq1.`, three dot-separated parts, at most 512 characters) so an obviously wrong QR is refused without a network call. The app does not verify the HMAC; the server does. Send `{ "method": "qr", "qr_token": ... }`.
- [ ] One-shot geolocation path for when the QR is not available. Send `{ "method": "geofence", "latitude", "longitude", "accuracy_m" }`. The server does the 30 m geofence check and refuses a poor fix. Do not log, store or show the coordinates.
- [ ] States: scanning, submitting, success ("Checked in: Building X, N min left"), and errors. Building X comes from `GET /buildings` by `building_id`; N is the minutes from now to `valid_until`, rounded down. If the building list fails, show "Checked in" and the minutes without a name rather than failing the check-in.
- [ ] Error mapping by the problem `type` slug, each with a next step: `qr-malformed` and `qr-invalid` (not a FloorWars entrance code, try the geolocation check-in), `qr-expired` and `qr-not-yet-valid` (the code is out of date or the phone clock is wrong), `building-unknown`, `outside-geofence` (move closer to the building or scan the QR), `location-inaccurate` (wait for a better fix, move near a window or outside), 401 (sign in again, through the refresh flow), 503 and network errors (try again), permission denied (say what is lost, offer the other method and the settings link).
- [ ] Camera and location permissions are requested only when the user taps to check in.
- [ ] A second check-in replaces the first on the server; the success state shows the new one.
- [ ] **Blocked on Cristea:** choose a QR scanner library and a geolocation library. Write the parse and state code first, behind a small interface so the library is a one-file change. Put both options under "Blocked" with licence and last release date. Install only the one Cristea picks.
- [ ] Jest tests: QR parsing (valid, malformed, expired-looking), every state mapping, and the minutes-left calculation.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`. Paste the summary lines.
- Done when: the tests pass, and the click-through against the Prism mock is recorded element by element in the PR description.

### W2-7 Integration and exit (last)

*Done in this session, not delegated. Runs after all agents report.*

- [ ] App CI: add `.github/workflows/app.yml` on `feat/w2-auth` (pull requests touching `app/**` or `contracts/**`: Node 24, `npm ci`, lint, typecheck, `npm test`, then `npm run generate:api` and `git diff --exit-code app/src/api/schema.ts`). Follow the style of `server.yml`.
- [ ] Open one PR per branch into `main`. Ask Ionut for review on the contract-facing parts (auth, check-in). The segmenter PR carries the confusion matrix from `docs/evaluation.md`.
- [ ] **Staging switch (waits for the VM):** when Ionut says the VM runs, check `https://api.floorwars.me/healthz`, change the base URL setting from `mock` to `production`, and run `tools/e2e/e2e_check.py` once with your own university address to confirm the server still matches the contract. Not before the VM is up. Until then each PR says "tested against the Prism mock only".
- [ ] On a real phone (not claimed until Cristea runs it): sign up, pick team, scan an entrance QR (made with `tools/qr/make_entrance_qr.py`, key from SOPS), see "Checked in: Building X, N min left". Also: sign out and back in, kill the app and reopen it (still signed in), check in by geolocation next to a building, and try an expired or foreign QR. List these as Cristea's phone checks in the PR. Do not mark them done.
- Done when: each PR's CI is green, and the report lists the phone checks Cristea must run and the staging switch as pending on the VM.

## 4. Report format

After each checklist item, post one line: `W2-n done | verify: <command> → <summary line> | commit: <sha>`. Agents post the same line in their reports. Copy them here after you have re-run the verify command. Keep these sections up to date in your final report:

- **Blocked:** items waiting on Cristea or Ionut, one line each, with the default you would use.
- **Decisions:** choices you made (library, window length, folder), one line each, with the reason.
- **Phone checks for Cristea:** only items you could not run here.

If the Android build or the Node tests cannot run on this machine, say so and list what you verified by reading the code.

## 5. Exit for Week 2

- Segmenter and classifier pass their tests. The confusion matrix is in `docs/evaluation.md`.
- Auth flow and check-in screen pass Jest and work against the Prism mock, and their PRs are open.
- The trace-replay workflow and the app workflow exist.
- Blocked items are listed with a default each.
- The staging switch and the phone checks are listed as pending on the VM, for Cristea to run. They are not claimed.
