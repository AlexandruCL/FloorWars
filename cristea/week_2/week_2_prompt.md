# Prompt: Cristea's Week 2 implementation (FloorWars)

You are implementing Cristea's part of Week 2 in `D:\FloorWars`. Work in one session, on a feature branch from `main`. Follow the checklist in section 3 in order, except where a step says it can run in parallel. Tick each box only after its verification command has run and passed.

## 0. Ground rules

- **Read only the docs in section 2.** Do not read the rest of `IMPLEMENTATION_PLAN.md`, Ionut's `/server` code, or the Week 3 to 6 plan. If you need something outside the list, say which file and why before opening it.
- Codebase questions: `graphify-out/` exists, so run `graphify query "<question>" --budget 1500` (or `graphify path`, `graphify explain`) before reading files. Read files only for the lines you need.
- Contract first. Do not edit `contracts/openapi.yaml`. Contract changes are PRs reviewed by Ionut. If the contract blocks you, write the question under "Blocked" in section 4 and go on with other items.
- Do not edit `app/src/api/schema.ts` by hand. Regenerate it with `npm run generate:api` in `app/`.
- Do not install a new dependency without Cristea's approval. Name the candidates, their licence and last release date, and wait for the answer.
- Do not commit real sensor recordings. Read the header of each CSV before any commit (`docs/trace_format.md`).
- Branches: `feat/w2-segmenter` for section W2-1 to W2-4, `feat/w2-auth` for W2-5, `feat/w2-checkin` for W2-6. One PR per branch into `main`. Do not run `git checkout` on `main` in a way that loses uncommitted work.
- Before you claim any item done, run its verification command and paste the summary line into your report. No claim without output.
- If a root cause is unclear for a failing test, find the cause first, then fix. Do not patch around a symptom.

## 1. Current state (checked 2026-10-27)

- Week 1 is done on code and synthetic data. Real-phone checks and real labelled traces are **not done** (`cristea/week_1/phone_tests.md`). `fixtures/real_data/` holds 4 real CSVs (stairs_up, stairs_down, elevator_up, blow, all hand placement) as of 2026-10-27. They are untracked, so not committed. Week 1 exit needs 20 across all six labels and two phones.
- `app/android/app/src/main/java/com/floorwars/floorsensors/segmenter/Segmenter.kt` and `classifier/Classifier.kt` are 4-line stubs. `classifier/StepScoring.kt` already has the steps-per-metre scoring rule and its thresholds. Do not duplicate it.
- `TraceCsv.kt` and `SensorEventBuffer.kt` already hold the sample and event types. Reuse them. Do not invent parallel types.
- Auth is a stub: `app/src/auth/authStub.ts` (Keychain, dummy token) and `DEV_SKIP_SIGN_IN` in `app/src/config/devFlags.ts`. `app/src/api/client.ts` and `schema.ts` exist. Sign-in and check-in screens are placeholders in `app/src/screens/PlaceholderScreens.tsx`.
- Trace folder: the spec says `/traces`, the repo uses `fixtures/`. Use `fixtures/synthetic/` and `fixtures/real_data/` until Cristea decides otherwise. Do not move files.
- `docs/evaluation.md` does not exist yet. You create it in W2-3.

## 2. Documents to read (and only these)

| Doc | Which part | Needed for |
|---|---|---|
| `IMPLEMENTATION_PLAN.md` | Section 10, "Week 2" (Cristea and exit lines only) | All |
| `IMPLEMENTATION_PLAN.md` | Section 3.3, "Sensor fusion" | W2-1, W2-2 |
| `IMPLEMENTATION_PLAN.md` | Section 7.9 (auth pattern) and section 8 (data minimisation, input validation) | W2-5, W2-6 |
| `IMPLEMENTATION_PLAN.md` | Section 11 (evaluation), first row group only | W2-3 |
| `IMPLEMENTATION_PLAN.md` | Section 9.2 (working rules) and 9.3 (Week 2 integration row) | W2-7 |
| `docs/trace_format.md` | Sections 1, 3, 4 (checks), 7 (validation log) | W2-1 to W2-4 |
| `fixtures/synthetic/README.md` | Whole file (short) | W2-3 |
| `tools/validate_traces/validate.py` | Constants block and check 9 only | W2-2 |
| `contracts/openapi.yaml` | Paths `/auth/otp`, `/auth/verify`, `/auth/refresh`, `/teams`, `/seasons/{id}/join`, `/checkins`, and the schemas they reference (`CheckinRequest`, `Checkin`, `Problem`) | W2-5, W2-6 |
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

- [ ] Run `git status` and `git branch --show-current`. Note that `cristea/week_2/prompt_week2.md` is deleted in the working tree. Do not restore it unless Cristea asks.
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

- [ ] JUnit harness that runs the segmenter and classifier on every CSV in `fixtures/synthetic/` (and `fixtures/real_data/` if it has files). Read the label and placement from the CSV header and `labels.csv`.
- [ ] Print a confusion matrix (counts per label and per predicted class) and the file count. The harness never writes to `fixtures/`.
- [ ] Create `docs/evaluation.md` with three sections: "Confusion matrix", "Baseline", "Validation log". Baseline states that numbers come from synthetic data unless the real set is present. Synthetic numbers are not evaluation (`fixtures/synthetic/README.md`).
- [ ] Record the commit SHA and the data folder used in the Baseline section.
- Verify: `cd app/android && ./gradlew test`, and paste the confusion matrix.
- Done when: the matrix prints, the doc has the three sections, and Cristea has the numbers to review.

### W2-4 Real-data gate (runs in Track A, blocked on Cristea)

*Delegate: `w2-replay-harness`, as the last step of its run.*

- [ ] Check `fixtures/real_data/` and `labels.csv`. Count the traces per label and per phone.
- [ ] If there are fewer than 20 real labelled traces, or any label is missing, write that in the Baseline section and under "Blocked" in section 4. Do not tune thresholds on synthetic data alone.
- [ ] If real traces exist: run `python tools/validate_traces/validate.py fixtures/real_data` and log the result in the validation log of `docs/trace_format.md` section 7. Tune a threshold only with logged evidence, and only in the constants block.
- Done when: the gate status is written down, with the counts.

### W2-5 Auth screens, token storage, refresh (Track B, React Native)

*Delegate: `w2-auth-ui` (worktree `D:/FloorWars-w2/auth-ui`).*

- [ ] Screens: e-mail entry, OTP entry (6 digits), team choice. Call `POST /auth/otp`, `POST /auth/verify`, `GET /teams`, `POST /seasons/{id}/join` through the generated client.
- [ ] Replace the stub in `authStub.ts` with the real flow. Keep the access token and refresh token in `react-native-keychain` (Android Keystore). Keep `DEV_SKIP_SIGN_IN` as it is for the friend build.
- [ ] Refresh interceptor: on 401, call `POST /auth/refresh`, store the new refresh token (rotation), retry once. If the server reports reuse, sign out and clear the Keychain entry.
- [ ] Each screen has loading, empty, and error states. Errors say what the user can do next.
- [ ] Jest tests: refresh rotation, reuse leading to sign-out, and the states of each screen. Use `react-native-testing` patterns.
- [ ] Run the generated-client check: `npm run generate:api`, then `git diff --exit-code app/src/api/schema.ts` must pass unless `contracts/openapi.yaml` changed.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`, and `npm run generate:api`. Paste the summary lines.
- Done when: all Jest tests pass, and the flow works against the Prism mock in `contracts/prism/` (state how you ran it).

### W2-6 Check-in screen: QR and geolocation (Track B, React Native)

*Delegate: `w2-checkin-ui` (worktree `D:/FloorWars-w2/checkin-ui`), after W2-5 per section 3.1.*

- [ ] Screen reached from the main navigator.
- [ ] QR parse: read the signed rotating token from the scanned payload. The app does not verify the HMAC; the server does. Send the token as `CheckinRequest` describes.
- [ ] One-shot geolocation path for when the QR is not available. The server does the 30 m geofence check.
- [ ] States: scanning, submitting, success ("Checked in: Building X, N min left"), and errors (expired token, rejected token, outside geofence, permission denied). Each error has a clear next step.
- [ ] Camera and location permissions are requested only when the user taps to check in.
- [ ] **Blocked on Cristea:** choose a QR scanner library and a geolocation library. Write the parse and state code first. Put both options under "Blocked" with licence and last release date. Install only the one Cristea picks.
- [ ] Jest tests: QR parsing (valid, malformed, expired-looking) and every state mapping.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`. Paste the summary lines.
- Done when: the tests pass, and the click-through against the Prism mock is recorded element by element in the PR description.

### W2-7 Integration and exit (last)

*Done in this session, not delegated. Runs after all agents report.*

- [ ] When Ionut posts the staging URL, switch the client from the mock to staging. Sign-in works on a phone against staging.
- [ ] On a real phone (not claimed until Cristea runs it): sign up, pick team, scan an entrance QR, see "Checked in: Building X, N min left". List these as Cristea's phone checks in the PR. Do not mark them done.
- [ ] Segmenter produces a confusion matrix on the traces (W2-3 output, real set if available).
- [ ] Open one PR per branch into `main`. Ask Ionut for review on the contract-facing parts (auth, check-in).
- Done when: each PR's CI is green, and the report lists the phone checks Cristea must run.

## 4. Report format

After each checklist item, post one line: `W2-n done | verify: <command> → <summary line> | commit: <sha>`. Agents post the same line in their reports. Copy them here after you have re-run the verify command. Keep these sections up to date in your final report:

- **Blocked:** items waiting on Cristea or Ionut, one line each, with the default you would use.
- **Decisions:** choices you made (library, window length, folder), one line each, with the reason.
- **Phone checks for Cristea:** only items you could not run here.

If the Android build or the Node tests cannot run on this machine, say so and list what you verified by reading the code.

## 5. Exit for Week 2

- Segmenter and classifier pass their tests. The confusion matrix is in `docs/evaluation.md`.
- Auth flow and check-in screen pass Jest, and their PRs are open.
- Blocked items are listed with a default each.
- Phone checks are listed for Cristea, not claimed.
