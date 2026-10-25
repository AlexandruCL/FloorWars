# Prompt: Orchestrator, Cristea's Week 2 (FloorWars)

## Start here: what to type into the first session

Open this session first. It becomes the orchestrator (`w2-orch`).

1. Open a new Claude Code session in `D:\FloorWars`.
2. Type `/rename w2-orch`
3. Type `/model opus` (Claude Opus, `claude-opus-5-5`)
4. Type `/effort high`. If `/effort` does not exist in your build, skip it and tell the orchestrator.
5. Switch to plan mode: press Shift+Tab until the mode indicator says plan.
6. Paste this line:

> Read `D:\FloorWars\cristea\week_2\prompt_week2.md` in full and follow it. Start with the preflight in step 0.

**After a pause or session limit (same week, new sessions):** open the orchestrator and the five lane sessions again, and rename and set model and effort as before. Do not reopen the old sessions. In the orchestrator, do steps 1 to 5 the same way, then paste this in step 6 instead:

> Resume Week 2. Read `D:\FloorWars\cristea\week_2\prompt_week2.md` in full and follow it. Start with the preflight in step 0. Then resume from `progress.md`.

For the lane sessions, you only open them, rename them, and set model and effort, as before. You do not paste resume lines into them. Once the orchestrator's preflight passes, it sends each lane its resume message itself (section 7). If a lane session is not listed by `ListAgents`, the orchestrator tells you which one to open.

Why Opus at high effort: the orchestrator plans the split, routes handoffs, keeps the resume file, and decides when a lane is blocked. Those calls matter more than speed. The lanes do the heavy coding in their own sessions.

You are the orchestrator for Cristea's Week 2 in FloorWars (repo `D:\FloorWars`). You run in one session. Cristea opens five other Claude Code sessions by hand, and you delegate work to them and to subagents you start yourself. You plan, split, set up, route messages, watch the board, and check the exit gates. You do not write lane feature code yourself.

Read this file in full before you do anything else.

**Step 0: preflight. This is your first action, before any plan.** Run `ListAgents`. Check that the five manual sessions are open and named exactly: `w2-lead`, `w2-seg`, `w2-replay`, `w2-auth`, `w2-checkin`. Do not create worktrees, skills, the board, or a plan yet.

- If any session is missing or has the wrong name, stop. Tell Cristea which ones are missing, and give this checklist for each: open the session, run `/rename` with its name, then set `/model` and `/effort` from the table in section 3. Then wait. Do nothing else while you wait. When Cristea says they are done, run `ListAgents` again. Repeat until all five pass.
- You cannot read another session's model or effort. Once the names pass, ask Cristea to confirm that each session's model and effort match the table. Wait for that confirmation.
- Only when the names and settings are confirmed, continue. If `D:\FloorWars\cristea\week_2\progress.md` exists (section 13), read it and resume from its Next actions instead of planning again. An approved plan recorded there stays approved unless Cristea changes it. Otherwise, start in plan mode. Your first reply is the plan only (section 12). Wait for Cristea's approval before you create worktrees, skills, or the board, and before you message any session.

## 1. What you can and cannot do

Be precise about this with Cristea in your plan. Do not promise more than these tools allow.

- **You can** send a message to another Claude session on this machine with `SendMessage`, but only to sessions that `ListAgents` shows. Check `ListAgents` at the start, and again after each delegation. If a session is not listed, Cristea must relay the message by pasting it.
- **You can** start subagents with the `Agent` tool and set each one's `model` (`opus`, `sonnet`, `haiku`) and `effort` (`low` to `max`). Use this for work that does not need a manual session, such as creating the skills, copying folders, running `generate:api`, and reading board or docs files. Use `isolation: "worktree"` when a subagent writes code.
- **You cannot** rename another session, change its model, or set its effort. Those are slash commands (`/rename`, `/model`, `/effort`) that Cristea types in each session. If one of these commands is not available in this build, say so and give Cristea the nearest alternative. Do not assume a command exists. Check it with `/help` in one session first.
- **So for each manual session**, your plan gives Cristea a one-line setup card: the name to give it, the model, the effort, the lane brief to read, and the first message to send. Cristea applies the name, model, and effort by hand, then the session starts.

## 2. Facts already established (do not redo)

- Week 1 code is done and merged. The app is React Native 0.88.0 in `app/`, Android `applicationId` is `com.floorwars`. Kotlin module `FloorSensors` is in `app/android/app/src/main/java/com/floorwars/floorsensors/`.
- `Classifier.kt` and `Segmenter.kt` are empty stubs. `StepScoring.kt` is the working scoring rule (4 to 8 steps per metre, ascent 2.0 to 120.0 m, steps 1 to 2000). Reuse it. Do not copy its numbers into a second place.
- Real phone work is still open (`cristea/week_1/phone_tests.md`, sections 1 to 5). Two phones have real recordings: Samsung SM-S918B (has a barometer) and SM-A325F (no barometer). The segmenter must report "no barometer" for SM-A325F. It must never invent pressure features.
- On 2026-10-25 the trace checker thresholds were loosened from the first real SM-S918B recordings (commit `cbe3b1d`). Before that, 5 of 6 real traces passed.
- `fixtures/real_data/` is empty in this checkout. The real CSVs are not committed, because the privacy decision is still open. Lanes read real traces by absolute path from the main checkout (`D:\FloorWars\fixtures\real_data`). Never copy real CSVs into a worktree or a commit.
- Classifier starting thresholds come from `IMPLEMENTATION_PLAN.md` section 3.3 (the table "Starting thresholds for the rules classifier"). They are tunable from real data, and every change needs logged evidence.
- The API contract is `contracts/openapi.yaml`. Paths used this week: `/auth/otp`, `/auth/verify`, `/auth/refresh`, `/teams`, `/seasons/{id}/join`, `/checkins`, `/me`. Contract changes need a reviewed PR by Ionut. No lane edits the contract.
- The generated client is `app/src/api/schema.ts`, made with `npm run generate:api` in `app/`. Its output must stay byte-identical unless the contract changes.
- Auth is a stub in `app/src/auth/authStub.ts` (react-native-keychain, dummy token). `DEV_SKIP_SIGN_IN` in `app/src/config/devFlags.ts` stays for friend builds until Cristea decides to remove it.
- Prism mock config for the contract: `contracts/prism/README.md`. Lanes LC and LD use it until Ionut posts the staging URL on the board.
- Ionut's Week 2 items (auth endpoints, `/checkins`, seed data, staging deploy) are Ionut's. No lane implements server code.
- Open decisions due in Week 2: the CI precision threshold for the trace-replay gate (Cristea, plan section 15.3). The university e-mail domain allow-list (Ionut).
- Contract version: `info.version` in `openapi.yaml` still reads `0.1.0-draft`, while the README records the 0.2.0-draft territory revision. Report this to Cristea. Do not change it.
- The main checkout `D:\FloorWars` has local changes that belong to no lane (the Week 1 docs were moved to `cristea/week_1/`, and `cristea/week_2/` holds this prompt). Lanes never touch `.gitignore`, and never commit those files.
- Today is 2026-10-25. Week 2 rhythm: Monday plan, Thursday integration (20 minutes each, Cristea and Ionut), Friday tag a demoable build.

## 3. Lanes and sessions

Five manual sessions plus this orchestrator session. Give each manual session the name below, then set its model and effort as shown. Cristea applies those settings by hand, and you tell them the exact commands in your plan.

| Session name | Role | Worktree and branch | Model | Effort |
|---|---|---|---|---|
| `w2-lead` | Lead: docs, board upkeep, README status, `docs/devices.md`, Ionut asks | `D:/FloorWars-w2/lead`, `docs/week2-status` | sonnet | medium |
| `w2-seg` | LA: segmenter v1 (Kotlin) | `D:/FloorWars-w2/segmenter`, `feat/w2-segmenter` | opus | high |
| `w2-replay` | LB: classifier v1 and trace-replay harness | `D:/FloorWars-w2/classifier-replay`, `feat/w2-classifier-replay` | opus | high |
| `w2-auth` | LC: auth screens, token refresh, client wiring | `D:/FloorWars-w2/auth-ui`, `feat/w2-auth-ui` | sonnet | medium |
| `w2-checkin` | LD: check-in screen (QR and geolocation) | `D:/FloorWars-w2/checkin-ui`, `feat/w2-checkin-ui` | sonnet | medium |

The orchestrator is the session you are in now. Name it `w2-orch`. Its own model and effort are set by Cristea, not by you.

You may change a row if the task needs it (for example, drop LC to haiku for a copy-only task). Say why in the plan. For the subagents you start yourself, pick the model and effort per task using the same reasoning: opus and high for algorithms and concurrency, sonnet and medium for UI and integration, haiku and low for mechanical work such as copying folders, running a generator, and reading files.

## 4. Skills to create (with skill-creator)

Create these three skills with the `anthropic-skills:skill-creator` skill. Do it yourself or in a subagent (sonnet, medium). Save each to `D:\FloorWars\.claude\skills\<name>\SKILL.md`. Then copy the folder into every worktree, because Git does not track `.claude`.

1. **`session-board`.** How to read and write the board: section ownership, line format, re-reading before each edit, closing items with a commit SHA, and how to ask `For Cristea` and `For Ionut`. Used by all sessions.
2. **`trace-replay-eval`.** Run the trace harness on a directory given by absolute path. Print the confusion matrix as counts per label and per class, and state the commit SHA and the path. Write numbers into the Baseline section of `docs/evaluation.md` only when asked. It never writes to `fixtures/`. Used by `w2-seg`, `w2-replay`, and `w2-lead`.
3. **`api-client-regen`.** Run `npm run generate:api` in `app/`, check that `app/src/api/schema.ts` is unchanged unless `contracts/openapi.yaml` changed, run the contract tests (`app/__tests__/apiContract*`), and report the summary line. Used by `w2-auth` and `w2-checkin`.

The React Native skills (`react-native-best-practices`, `react-native-testing`, `vercel-react-native-skills`) are already installed. The antislop skills cover UI and copy. No Kotlin skill is needed; Kotlin rules are in the lane briefs. Keep each `SKILL.md` short, and say what triggers it and which files it touches. Ask Cristea only if a skill needs a decision.

## 5. Setup (after plan approval)

Do these in order. Report each one with its result.

1. **Board.** Create `D:\FloorWars\.claude\board\week_2.md` (section 6). It is outside every worktree and ignored by Git through `.claude/`. Never commit it.
2. **Worktrees.** From `D:\FloorWars`, branching from `main`:
   ```
   git worktree add D:/FloorWars-w2/lead -b docs/week2-status main
   git worktree add D:/FloorWars-w2/segmenter -b feat/w2-segmenter main
   git worktree add D:/FloorWars-w2/classifier-replay -b feat/w2-classifier-replay main
   git worktree add D:/FloorWars-w2/auth-ui -b feat/w2-auth-ui main
   git worktree add D:/FloorWars-w2/checkin-ui -b feat/w2-checkin-ui main
   ```
   Do not run `git checkout` in `D:\FloorWars`. Check `git worktree list` afterwards.
3. **Skills.** Create them (section 4), then copy `.claude\skills` into each worktree.
4. **Dependencies.** Each lane installs what the repo already declares (`npm ci` in `app/` for LC, LD; Gradle on first build for LA, LB). Adding a new dependency needs Cristea's approval (section 8).
5. **Lead docs.** `w2-lead` creates the `docs/evaluation.md` skeleton (sections: confusion matrix, Baseline, validation log). LB owns the Baseline section only.
6. **Check the sessions.** Run `ListAgents`. Note which of the five names appear. Report the list to Cristea.

## 6. Board (how the sessions talk)

File: `D:\FloorWars\.claude\board\week_2.md`.

```
# Week 2 board

## Lead (w2-lead)
Status:
Inbox:

## LA segmenter (w2-seg)
Status:
Inbox:
Outbox:

## LB classifier-replay (w2-replay)
Status:
Inbox:
Outbox:

## LC auth-ui (w2-auth)
Status:
Inbox:
Outbox:

## LD checkin-ui (w2-checkin)
Status:
Inbox:
Outbox:

## Orchestrator (w2-orch)
Status:
Routing log:

## For Cristea (decisions only)

## For Ionut (lead writes, Cristea forwards)
```

Rules every session follows:
- Re-read the board right before every edit. Another session may have changed it.
- Write only in your own section. To ask another lane something, add a line to that lane's Inbox.
- Line format: `- [YYYY-MM-DD HH:MM] from <session>: <ask or handoff> | needs: <what> | status: open`. Close an item with `done` or `answered` and the commit SHA.
- Handoffs go in your Outbox and in the receiver's Inbox.
- Update your `Status:` line at each commit.
- Cristea's decisions go under `For Cristea`. One line each, with a recommended answer. If you can pick a sensible default, pick it, say so, and do not wait.
- `SendMessage` is a nudge, not the record. The board is the record. You (the orchestrator) mirror every message you route into the Routing log.

## 7. Routing and delegation

**Resume messages (after a pause or session limit):** send each listed lane session its resume message yourself, with `SendMessage`. Use this text, with the lane's name and letter filled in: "You are `<name>` (lane `<letter>`). Resume Week 2. Read `D:\FloorWars\cristea\week_2\prompt_week2.md` sections 2, 3, 8 (lane `<letter>`), 9, and 10. Check `git status` in your worktree and your board section first, then continue from your Next step." Lane names: `w2-lead` (L0), `w2-seg` (LA), `w2-replay` (LB), `w2-auth` (LC), `w2-checkin` (LD). Send to every lane that `ListAgents` shows. Then report to Cristea which lanes acknowledged, and which need to be opened or renamed.

For each lane, follow this loop.

1. Confirm the session is listed by `ListAgents`. If not, give Cristea the paste text for that session and wait for them to confirm it is open.
2. Send the first message with `SendMessage`: "You are `<session name>`. Read `D:\FloorWars\cristea\week_2\prompt_week2.md` sections 2, 3, 6, 7 (only the row for your lane), 8, and 9. Start in plan mode. Your first reply is the plan only." Include the lane's section number so the session reads its own brief.
3. When a session posts a plan, check it against the lane brief and the rules. Send the approval, or send the change request with the reason. Show Cristea any plan that touches a dependency, a contract file, or a decision.
4. When a session posts a handoff, read its Outbox entry and forward it to the receiver's Inbox with a `SendMessage` nudge. Add one line to the Routing log.
5. When a session asks `For Cristea`, collect the question into one list and ask Cristea once, with the defaults you would use. Do not ask Cristea the same thing twice.
6. When a session asks `For Ionut`, write it into the `For Ionut` section. Cristea forwards it. Do not contact Ionut directly.

Dependency order for merges (Cristea merges, you report readiness):
- `w2-seg` first. Publishes the interface in section 9 of this file.
- `w2-replay` after `w2-seg` publishes the interface, and can start harness work before that.
- `w2-auth` and `w2-checkin` run in parallel with the segmenter lanes, against the Prism mock.
- `w2-lead` merges docs as each lane lands.

If a session is not listed by `ListAgents`, or `SendMessage` fails, stop routing to it. Tell Cristea which session is unreachable and what to paste. Keep the rest of the work going.

Use subagents (section 5 and section 4) for work that does not need a manual session. Do not start a second implementer for a lane that already has a manual session. That would duplicate work and cause conflicts.

## 8. Lane briefs

Each lane session reads its own brief here and nothing else from the lanes' sections, except sections 2, 8 and 9.

### L0 Lead (`w2-lead`, branch `docs/week2-status`)

**Goal:** the board, docs, and status stay correct while four lanes build.

**Scope:** `docs/evaluation.md` skeleton and its non-Baseline sections. `docs/devices.md`: phone details for SM-S918B and SM-A325F, once Cristea confirms them. README "Status" and "Decisions taken" (dated rows). The `For Ionut` section, and any staging or QR-format request Ionut needs.

**Done when:** the skeleton is committed on `docs/week2-status`. The README status says Week 2 is in progress. Each lane has a Status line on the board that matches its commits.

### LA Segmenter (`w2-seg`, branch `feat/w2-segmenter`)

**Goal:** segmenter v1 detects ascent windows from pressure and step events, offline, in pure Kotlin.

**Scope:**
- `app/android/app/src/main/java/com/floorwars/floorsensors/segmenter/Segmenter.kt`
- Smoothing: pressure low-pass or median. Pick one, and justify it in a short code comment.
- Ascent-window detection: windows from 5 s to 3 min (plan 3.3). Produce the features in section 9.
- Pressure-steps match flag: the same rule as `StepScoring.kt`. Call into that file. Do not copy it.
- No barometer: return an empty result and say so in the return type or a documented value. Do not fake a value.
- Tests in `app/android/app/src/test/java/com/floorwars/floorsensors/segmenter/SegmenterTest.kt`. Use hand-built pressure ramps (one climb, one flat walk, no ascent), and one run over `fixtures/synthetic`.
- Pure Kotlin, no Android imports.

**Depends on:** nothing. Publishes the section 9 interface on the board before `w2-replay` writes code against it.

**Done when:**
- `cd app/android && ./gradlew testDebugUnitTest` passes. Report the summary line.
- ktlint passes, if configured in this project. Check the Gradle task name first and report it.
- The section 9 interface is on the board, with the commit SHA in its Outbox.
- The feature table for `fixtures/synthetic` is written to the scratchpad, not committed.

### LB Classifier and trace replay (`w2-replay`, branch `feat/w2-classifier-replay`)

**Goal:** rules classifier v1, a JUnit trace-replay harness, and the first confusion matrix.

**Scope:**
- `app/android/app/src/main/java/com/floorwars/floorsensors/classifier/Classifier.kt`
- Rules from plan 3.3. Stairs: vertical speed 0.1 to 0.9 m/s and 4 to 8 steps per metre. Elevator: vertical speed above 1.0 m/s and below 1 step per metre. Everything else is `OTHER`.
- Reject shake (steps without ascent) and blow (pressure spike with no steps). The spike threshold is a named constant with a short comment. Log the value in `docs/evaluation.md`.
- Harness: a JUnit test that reads a traces directory and `labels.csv`, runs the segmenter and classifier, and prints a confusion matrix. The directory comes from the environment variable `FLOORWARS_TRACE_DIR`, default `fixtures/synthetic`. Real traces are passed by absolute path, never copied.
- All thresholds in one constants block. Each change needs a logged reason.
- Baseline numbers go in the Baseline section of `docs/evaluation.md`. LB owns that section only.
- Propose the CI precision threshold (plan 15.3) under `For Cristea`, with the number you measured and a default.

**Depends on:** `w2-seg`'s interface (section 9). Until it is published, write against the proposed signatures and say so in the Outbox.

**Done when:**
- `./gradlew testDebugUnitTest` passes with the harness included.
- The confusion matrix prints for `fixtures/synthetic` (24 labelled traces). If Cristea gives the real trace path, print it too. Report each matrix as a table of counts.
- The Baseline section has the numbers, the commit SHA, and the source path for each run.

**Skills:** `trace-replay-eval`, `session-board`.

### LC Auth UI (`w2-auth`, branch `feat/w2-auth-ui`)

**Goal:** the app signs in against a contract-shaped server (Prism mock now, staging later).

**Scope:**
- Screens: e-mail entry, OTP entry, team choice (`/teams`). Put them in `app/src/screens/`, next to `PlaceholderScreens.tsx`.
- Token storage stays in the Android Keystore through react-native-keychain. Keep the function names in `authStub.ts` (or its replacement) so `RootNavigator.tsx` keeps working.
- Refresh interceptor: on a 401, call `/auth/refresh`, store the new refresh token (rotation), and retry once. A reused refresh token (family reuse) signs the user out.
- Wire the generated client (`app/src/api/schema.ts`) through the `api-client-regen` skill. Do not hand-edit generated output.
- Keep `DEV_SKIP_SIGN_IN` working.
- Use the Prism mock (`contracts/prism/README.md`). No server code.

**Design direction:** the app has no `DESIGN.md`. Under antislop R-37, put a one-line question under `For Cristea` with the default you would use. Until the answer, label the screens "draft without direction" in the PR description, and use the antislop dials ENERGY 1 / RHYTHM 1 / MOTION 1.

**Depends on:** Prism mock now. Ionut's staging URL when it appears on the board.

**Done when:**
- `cd app && npm run lint`, `npx tsc --noEmit`, and `npm test` pass. Report the summary lines.
- Jest tests cover refresh rotation, reuse leading to sign-out, and the empty, loading, and error states of each screen (R-27).
- A click-through of every control against the Prism mock, recorded element by element (R-35).
- `npm run generate:api` leaves `schema.ts` unchanged unless the contract changed.

**Skills:** `api-client-regen`, `session-board`, `react-native-best-practices`, `react-native-testing`, `antislop`, `antislop-ui`, `antislop-layoutmobile`, `antislop-copywriting` (for on-screen text). Load them with the Skill tool before writing UI.

### LD Check-in UI (`w2-checkin`, branch `feat/w2-checkin-ui`)

**Goal:** the check-in screen scans the entrance QR or uses one-shot geolocation, then shows the result from `POST /checkins`.

**Scope:**
- Screen in `app/src/screens/`, reached from the main navigator.
- QR parse: read the signed rotating token from the scanned payload. The app does not verify the HMAC. The server does. Send the token as the contract describes.
- One-shot geolocation path, for when the QR is not available. The server does the 30 m geofence check.
- States: scanning, submitting, success ("Checked in: Building X, N min left"), and errors (expired token, rejected token, outside geofence, permission denied). Each error has a clear next step.
- Camera and location permissions are requested only when the user taps to check in.

**Dependencies, asked before installing:** a QR scanner library and a geolocation library. The plan leaves the choice open. Write the parse and state code first. Put both library options (licence, last release date) under `For Cristea`, and install only the one Cristea picks.

**Depends on:** Prism mock now. Ionut's seed data and QR format on the board when posted.

**Done when:**
- `npm run lint`, `npx tsc --noEmit`, and `npm test` pass. Report the summary lines.
- Jest tests cover QR parsing (valid, malformed, expired-looking payload) and every state mapping.
- A click-through against the Prism mock, recorded element by element (R-35).
- Real QR and GPS checks are listed for Cristea's phone session, not claimed as done.

**Skills:** the same UI and RN skills as LC, plus `session-board`.

## 9. Interfaces between lanes

`w2-seg` publishes these on the board first. Reuse the existing sample and event types in `TraceCsv.kt` and `SensorEventBuffer.kt`. Do not invent parallel types. The names below are the proposal. `w2-seg` may change them, and must post the change on the board.

Package `com.floorwars.floorsensors.segmenter` (pure Kotlin):

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

Package `com.floorwars.floorsensors.classifier`:

```kotlin
enum class Kind { STAIRS, ELEVATOR, OTHER }

class Classifier {
    fun classify(segment: Segment): Kind
}
```

Direction (up or down) comes from the sign of `ascentM`. The trace labels in `fixtures/synthetic/labels.csv` (`stairs_up`, `stairs_down`, `elevator_up`, `walk_flat`, `shake`, `blow`) map onto `Kind` in the harness only.

## 10. Rules for every session

- Branch per lane, from `main`. One PR per lane into `main`, reviewed by the other member. Commit after every subtask. Messages in `git log` style (`feat:`, `test:`, `docs:`, `chore:`).
- **Every commit excludes Claude as co-author.** No `Co-Authored-By` line naming Claude or any model, no "Generated with Claude Code" line, and no other AI attribution in the commit message body. This applies to every session, including subagents. Use only the commit message itself. After each commit, run `git log -1 --format=%B` and check that the message has no such trailer. If it does, amend it with `git commit --amend` before you report the commit (only on your own unpushed branch). Report that you checked.
- Never push, merge, open a PR, or touch `main` unless Cristea says so.
- No new dependency without Cristea's approval. Installing what the repo already declares is fine.
- Never commit: real CSVs, keystores, `google-services.json`, `.env*`, the APK, anything under `.secrets/`, `local.properties`, or the board file.
- Do not edit `contracts/openapi.yaml`, `server/`, `infra/`, `Ionut/`, `.gitignore`, or `IMPLEMENTATION_PLAN.md`. Ask through the board.
- Before any "done" claim: run the command and report its summary line. A failed test is reported as failed, with the test name.
- Bug or test failure: find the root cause first, then propose the fix.
- Keep output short. Long output goes to the scratchpad, and you cite the path.
- Real phone checks are Cristea's. No session claims a phone result it did not get.
- **Stopping and resuming.** Before a session limit or a pause, write `Next step:` and the list of uncommitted files in your board section, then stop. On start, read your board section, run `git status` in your worktree, and continue from `Next step`. Do not redo committed work.

## 11. Week 2 exit (the orchestrator tracks this)

From `IMPLEMENTATION_PLAN.md` section 10, Week 2: on a real phone, sign up, pick a team, scan the entrance QR, and see "Checked in: Building X, 89 min left". The segmenter produces a confusion matrix on the traces.

Week 2 is done when:
- `w2-seg` and `w2-replay` are ready to merge (Cristea merges), and the confusion matrix is in `docs/evaluation.md`.
- `w2-auth` and `w2-checkin` are ready to merge, and their click-throughs are recorded.
- The CI precision threshold has a decision on the board.
- Staging sign-in and check-in run on a real phone (Cristea's session, with Ionut on the staging side).

Report this list to Cristea at each Monday and Thursday sync, with the current status of each line.

## 12. Output

1. **First reply (plan only).** The plan must include:
   - The task breakdown from section 14, in full. Show counts per owner and the critical path. It is written to `D:\FloorWars\cristea\week_2\week_2_tasks.md` only after approval, because plan mode blocks file writes. Cristea approves the split together with the plan.
   - What you can and cannot do in this environment (section 1), in plain words.
   - The setup card for each manual session: name, worktree, branch, model, effort, and the exact `/rename`, `/model`, and `/effort` steps Cristea runs. Mark any command you have not confirmed exists.
   - The subagents you expect to use, with model and effort for each.
   - Any change you propose to the default model and effort table, with the reason.
   - Questions that block you. Keep them to what only Cristea can answer.
   Then wait for approval.
2. **After approval:** run the setup (section 5), send the first messages (section 7), and report `ListAgents` results. Then route, monitor, and report. End each report with the board status and the next decision you need from Cristea.

## 13. Progress file (for resuming after a session limit)

Cristea may hit a session limit and stop at any point. You keep one durable progress file so a new orchestrator session can pick up without asking what happened.

- **Path:** `D:\FloorWars\cristea\week_2\progress.md`. Create it with your first report, after the plan is written, not before.
- **Update it** at each of these moments: plan approved or changed, each setup step done, each session's status changes, each handoff routed, each decision from Cristea, each commit you see in a lane, and immediately before you stop because of a limit or a wait.
- **Keep it short.** Current facts only, and newest first in the log. Never copy long output, secrets, or real trace data into it.
- **Do not commit it** unless Cristea asks. It is a working note.

Use this layout:

```
# Week 2 progress (orchestrator)

Last updated: YYYY-MM-DD HH:MM
Phase: preflight | planning | setup | running | integration | blocked | done
Plan: approved YYYY-MM-DD (or: awaiting approval)

## Sessions
| Session | Lane | Worktree | Branch | Model | Effort | State | Last commit | Notes |
|---|---|---|---|---|---|---|---|---|
| w2-lead | L0 | ... | docs/week2-status | sonnet | medium | ... | ... | ... |
(one row per session, including w2-orch)

## Decisions for Cristea (open)
- ...

## Decisions made
- YYYY-MM-DD: ...

## Routing log (newest first)
- YYYY-MM-DD HH:MM: from ... to ...: ...

## Blockers
- ...

## Next actions (what to do first on resume)
1. ...
```

**Resume rule:** on a new orchestrator session, run the preflight (section 0) first, then read this file and the board (`D:\FloorWars\.claude\board\week_2.md`). Check each session's state in its own section of the board, and in `ListAgents`, before you route anything. For each worktree (`git worktree list`), run `git status` and `git log -1 --oneline` on its branch, and record the result in the Sessions table. Uncommitted files in a worktree mean that lane stopped mid-task. Route the lane's `Next step` to it, not new work. If a session has moved on since the last update, record the change, and ask it for its current status before you send new work.

If a session hits its own limit, record its state in the Sessions table as `paused at <last step>`, with the last commit. Tell Cristea which session to resume and what to type in it.

## 14. Task breakdown (checklist file)

Break the Week 2 specification into subtasks and put the breakdown in the plan. Plan mode blocks file writes, so write it to `D:\FloorWars\cristea\week_2\week_2_tasks.md` only after Cristea approves the plan. The file is the checklist for the whole week. After that, you update it as work moves. Sessions do not edit it. They report to you on the board, and you tick the boxes.

Use the seed list below as the starting point. Split, merge, or add subtasks where the specification needs it, and keep each one small enough to finish in one session sitting. Every subtask has exactly one owner.

**Seed subtasks**

Lead (`w2-lead`):
- L-01 Create the `docs/evaluation.md` skeleton (confusion matrix, Baseline, validation log).
- L-02 Fill `docs/devices.md` for SM-S918B and SM-A325F, after Cristea confirms the model strings.
- L-03 Keep the README "Status" table current for Week 2.
- L-04 Write Ionut's requests (staging URL, seed data, QR format) under `For Ionut`.
- L-05 Prepare the Monday and Thursday sync agendas.

Segmenter (`w2-seg`, opus, high):
- SEG-01 Publish the segment interface (section 9 of this prompt) on the board.
- SEG-02 Pressure smoothing: choose low-pass or median, document the choice in a short comment.
- SEG-03 Ascent-window detection, windows from 5 s to 3 min.
- SEG-04 Features: ascent, duration, vertical speed, steps, steps per metre, pressure-steps match (reuse `StepScoring.kt`).
- SEG-05 No-barometer path: empty result, no invented values.
- SEG-06 Unit tests: one climb, one flat walk, no ascent, and one run over `fixtures/synthetic`.
- SEG-07 Run `./gradlew testDebugUnitTest` and ktlint (if configured), and report the summary lines.

Classifier and replay (`w2-replay`, opus, high):
- RPL-01 Stairs, elevator, and other rules from plan 3.3 in `Classifier.kt`.
- RPL-02 Reject shake and blow. Name the spike threshold, and log its value in `docs/evaluation.md`.
- RPL-03 Harness: label loader and `FLOORWARS_TRACE_DIR` (default `fixtures/synthetic`).
- RPL-04 Confusion matrix for the 24 synthetic traces.
- RPL-05 Confusion matrix for the real traces, once Cristea gives the path.
- RPL-06 Baseline section of `docs/evaluation.md`: numbers, commit SHA, source path.
- RPL-07 Propose the CI precision threshold under `For Cristea`, with the measured number and a default.

Auth UI (`w2-auth`, sonnet, medium):
- AUTH-01 Screens: e-mail entry, OTP entry, team choice.
- AUTH-02 Keystore storage through the existing keychain wiring, keeping the `authStub.ts` function names.
- AUTH-03 Refresh interceptor: rotation, retry once, sign out on reuse.
- AUTH-04 Wire the generated client (`api-client-regen`).
- AUTH-05 Jest tests for refresh rotation, reuse, and the empty, loading, and error states.
- AUTH-06 Click-through against the Prism mock. Keep `DEV_SKIP_SIGN_IN` working.

Check-in UI (`w2-checkin`, sonnet, medium):
- CHK-01 QR payload parse, with tests (valid, malformed, expired-looking).
- CHK-02 Check-in screen states: scanning, submitting, success, each error.
- CHK-03 One-shot geolocation path, after Cristea picks the libraries.
- CHK-04 Request camera and location permission only on tap.
- CHK-05 Click-through against the Prism mock.

Cross-session and manual:
- X-01 Ionut posts the staging URL on the board (owner: Ionut, via Cristea). Unblocks AUTH-06 and CHK-05 against the real server.
- X-02 Real-phone sign-in and check-in (owner: Cristea, manual).
- X-03 Thursday integration sync (owner: Cristea and Ionut, manual).

Subagent-only work (owner: orchestrator, mark the model and effort on each line): creating the three skills, copying `.claude\skills` into worktrees, and running `npm run generate:api` checks when no lane session is active. Do not give a subagent work that a lane session already owns.

**File format**

```
# Week 2 tasks

Last updated: YYYY-MM-DD HH:MM
Source: IMPLEMENTATION_PLAN.md section 10 (Week 2), section 3.3, and prompt section 9.
Legend: [ ] todo  [~] doing  [x] done  [!] blocked (give the reason)

## Lead (w2-lead, sonnet, medium)

- [ ] L-01 Create the `docs/evaluation.md` skeleton
  - What: one short paragraph on what the subtask produces and why.
  - Owner: w2-lead. Model and effort: sonnet, medium.
  - Depends on: none.
  - Done when: the file is committed on `docs/week2-status` with the commit SHA recorded here.
  - Notes: (blank until work starts)

(one block for each subtask, grouped by owner)

## Cross-session and manual
...

## Critical path
- ...
```

Each subtask explains itself in one or two sentences, so Cristea can read the file without the rest of the prompt. Sessions get their own subtasks by pointing them at this file and the lane section in this prompt.

**Ticking the boxes:** a session reports on the board when it finishes a subtask, with its commit SHA. You then mark the box `[x]`, add the SHA and the date, and update the critical path. When a subtask is blocked, mark `[!]` with the reason and the owner who can unblock it. Mirror the counts (done, doing, blocked) in `progress.md`, not the full list.

## 15. Final walkthrough (Cristea's part of Week 2)

Write this only when every subtask in `week_2_tasks.md` is `[x]`, or `[!]` with a reason Cristea has accepted. Do not write it earlier. It covers Cristea's work: `w2-seg`, `w2-replay`, `w2-auth`, `w2-checkin`, and the `w2-lead` docs. Ionut's server work is mentioned only where Cristea's code depends on it.

**Validation first.** Before you write anything, re-run the checks in the lanes' worktrees, and quote the summary lines:
- `cd app/android && ./gradlew testDebugUnitTest` (segmenter, classifier, harness)
- ktlint, if the task exists (name it)
- `cd app && npm run lint`, `npx tsc --noEmit`, `npm test`
- The `trace-replay-eval` run on `fixtures/synthetic`, and on the real traces if Cristea gave the path
- `npm run generate:api` leaves `schema.ts` unchanged, unless the contract changed

If a check fails now, do not write the walkthrough. Put the failure in `For Cristea` and the owning lane's Inbox.

**Write `D:\FloorWars\cristea\week_2\week_2_walkthrough.md`.** Write it for Cristea, who should be able to explain the work afterwards without reading the code first. Plain language, short sections, file paths in backticks. Use this layout:

```
# Week 2 walkthrough (Cristea)

Date: YYYY-MM-DD
Status: all subtasks done | done with accepted exceptions (list)
Branches: feat/w2-segmenter, feat/w2-classifier-replay, feat/w2-auth-ui, feat/w2-checkin-ui, docs/week2-status (and the commit SHAs that merged or are ready)

## What you built, in one paragraph
(what the week delivered, end to end, in plain words)

## 1. Segmenter (LA)
- What it does, with the input (pressure and step events) and the output (segments).
- Key decisions: smoothing choice and why, window range, the no-barometer case.
- Where: file paths.
- How to run: the exact command.
- What you should check yourself: the one thing to read first.

## 2. Classifier and trace replay (LB)
- Rules (stairs, elevator, other) with the thresholds in one block, and where they come from (plan 3.3).
- Shake and blow rejection, and the spike threshold with its logged value.
- The harness: how to point it at a folder, and what the confusion matrix shows.
- Results: the matrix for synthetic traces, and for real traces if run. Quote the numbers and the commit SHA.
- What the numbers do not show yet (small sample, one phone, synthetic bias).

## 3. Auth screens (LC)
- The three screens and the flow between them.
- Token storage and the refresh rotation. Explain what happens on reuse (sign-out).
- The generated client and how it is regenerated.
- The stub and `DEV_SKIP_SIGN_IN`: what is still stubbed, and what is real.

## 4. Check-in screen (LD)
- The flow: scan QR or use geolocation, then the result.
- Each state and its message, including the errors.
- Permissions: when they are asked.
- The libraries chosen (from Cristea's decision) and why.

## 5. Docs and decisions (lead)
- What changed in `docs/evaluation.md`, `docs/devices.md`, and the README.
- Decisions taken this week, with dates (move them to the README decision table if the lead has not).

## 6. How it fits with Ionut's side
- What your code expects from the server (endpoints, QR format, staging URL) and whether each was met.
- Anything still on Prism mock, and what replaces it.

## 7. Not done, and why
- Real-phone checks (sign-in, check-in, QR, GPS) that were not run by a session. List them for Cristea's phone session.
- Open decisions, with the default used.

## 8. Known risks
- Three to five, each with what would reduce it.

## 9. Try it yourself (about 20 minutes)
1. Run the tests (the commands from the validation step).
2. Open the segmenter's test file and one real trace in a spreadsheet, and check one segment by hand.
3. Open the classifier's constants block and change one threshold locally, and watch the matrix move. Revert it.
4. Start the app against the Prism mock and walk the sign-in and check-in flow.
5. Write down one thing you disagree with. That goes to the Thursday sync.
```

Keep it to what you can verify. If a section has nothing to say, write "nothing this week" in that section instead of filling it. Do not claim a phone result, a number, or a screen that you did not see in a run.

**Then:** tick the walkthrough as a checklist item in `week_2_tasks.md` (owner: orchestrator), add its path to `progress.md`, and tell Cristea in one message: the walkthrough path, the validation summary lines, the open items in `For Cristea`, and the phone checks still to do.
