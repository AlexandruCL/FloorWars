# Prompt: Cristea's Week 4 implementation (FloorWars)

**Status: implementation in progress. Stopped on 2026-11-17 for a handoff. A new session continues from "Handoff" below, then follows the rest of this prompt.**

## Handoff (2026-11-17, read this first)

A new session that is told "continue cristea/week_4/week_4_prompt.md" starts here. Everything below was verified by the coordinating session (forced Gradle with `--rerun-tasks`, cold Jest with `--no-cache`) unless it says otherwise. Section 4 "Decisions" holds every answer Cristea gave on 2026-11-17; they are binding.

### Restore on a new machine

1. `git fetch origin` and check out `docs/w4-prompt` in the main checkout (it holds this file and the plan updates; it is not on `main` yet).
2. Recreate the worktrees from the pushed branches (no `-b`, the branches exist):
   ```
   git worktree add <root>-w4/contract feat/w4-contract
   git worktree add <root>-w4/seam     feat/w4-seam
   git worktree add <root>-w4/realtime feat/w4-realtime
   git worktree add <root>-w4/screens  feat/w4-screens
   git worktree add <root>-w4/fallback feat/w4-fallback
   git worktree add <root>-w4/tuning   feat/w4-tuning
   ```
   Then in each: copy `.claude/` as in section 3.1 and `cd app && npm ci`.
3. `.claude/` is gitignored. Cristea copies the `.claude` folder (with the five `w4-*` agents) to the new machine by hand; copy it into the main checkout and every worktree, then **restart the session** so the agents load.
4. Agents read this prompt by absolute path, because it is not on their branches: give them `<main checkout>/cristea/week_4/week_4_prompt.md`.
5. On this laptop: the emulator `cityconquest` (emulator-5554) and a Metro bundler on port 8081 (the realtime agent's) were left running. Stop Metro before starting your own.

### State per branch

| Branch | Head | Verified | Left to do |
|---|---|---|---|
| `feat/w4-contract` | `19cf2b9` | contract tests 3/3 at `91c6ea8`; the App test fix `c2e4eb4` cherry-picked as `19cf2b9` (full Jest not re-run after the cherry-pick) | PR, Ionut reviews |
| `feat/w4-seam` | `c2e4eb4` | Android 64/0, Jest 141/141, lint, tsc | PR |
| `feat/w4-realtime` | `9b7a16e` | at `16d421f`: Android 89/0, Jest 152/152 cold; break checks: dedupe removed → 5 fail, 10-min limit removed → 1 fails; emulator deep link cold and warm passed (agent's run) | **the catch-up fix below**, then re-verify `9b7a16e`+fix |
| `feat/w4-screens` | `861238c` | Android 64/0 forced, Jest 182/182, lint, tsc; break check: counting pending/rejected → 2 fail; packages `react-native-svg` 15.16.0, Reanimated 4.7.1, worklets 0.13.1 (all MIT) | click-through; cold-Jest slowness (below) |
| `feat/w4-fallback` | `911ca82` | Jest 174/174, lint, tsc; break check: cooldown removed → 3 fail | click-through |
| `feat/w4-tuning` | `866a409` | Android 64/0 forced, replay gate green; real 21 traces: precision and recall 1.00 per class; no threshold changed | plan-line conflict (below) |

Items: W4-0 done. W4-1 open (catch-up fix). W4-2, W4-3, W4-4, W4-5: code and tests done, emulator click-through not done. W4-6 done. W4-7 not done by Cristea's decision. W4-8 not started.

### Open work, in order

1. **W4-1 catch-up fix (send to `w4-realtime`, in its worktree).** `9b7a16e` makes only one *delivery* silent when no last event id is stored, but the backlog spans many: with `since=0` the server replays it as separate socket messages, so the 2nd..Nth old losses notify, and poll pages 2 to 5 of a `since=0` run notify too. Fix in `GameEventPipeline`: when an event arrives while no id is stored, record once a catch-up mark `catchUpBeforeMs = now` (injectable clock) in the realtime prefs, never overwriting an existing mark. A `building_flipped` whose `at` is before the mark is silent; at or after it, it notifies; a missing or unparseable `at` while a mark exists is silent. `clearRealtime` wipes the mark. Tests: socket replay of 3 old losses from `since=0` notifies none; a later live loss notifies; a 2-page poll from id 0 notifies none; a process restart keeps the mark. Then re-run both verify commands and the two break checks.
2. **W4-8 integration branch:** merge contract, seam, realtime, screens, fallback, tuning into a throwaway branch and run both verify commands. Expect: `RootNavigator.tsx`, `navigation/types.ts` and `HomeScreen.tsx` conflicts (merge order realtime, screens, fallback); screens tests that build `WsEvent` objects may need `event_id` (required since `91c6ea8`, after screens merged the contract at `acbb5b0`).
3. **Cold Jest on screens:** full cold run took 91 s against 34 s on the seam, and under load some first tests per file hit the 30 s timeout (seen in history, HomeScreen, leaderboards, checkin, AuthScreens). Turning off the worklets Babel plugin in Jest did not help. Cause not found. Measure again on the integration branch with nothing else running; CI runs cold.
4. **Click-throughs** on the emulator against Prism (`npm run mock:api`, `API_BASE_URL` pointed at `http://10.0.2.2:4010` locally, not committed), from one debug build of the integration branch: Home (today's figures, buttons), Standings, Leaderboards (3 tabs, season chips, building picker), History, Landing scan with `DEV_FORCE_NO_BAROMETER = true` (steps in the fallback agent's list: no check-in message, check in, heading and body, scan, `Scan counted`, cooldown, camera denied), Onboarding (first run after the team choice, not again after restart, "How it works"). Record element by element for the PR descriptions.
5. **PR order:** open `docs/w4-prompt` first (prompt, plan updates of `3619e35`, and the decisions). `feat/w4-tuning` edits the same plan line ("Classifier tuning pass 1 …"); when it rebases, keep the wording "pass 1 runs on the 21 existing real traces; no new traces were recorded this week" and drop the "20 traces" sentence. Then the section 0 order: contract, seam, realtime, screens, fallback, tuning, `docs/w4-finish`. `gh` is not installed: give Cristea branch, title and body.
6. W4-8 docs and the phone checks as in section 3.

### Blocked (waiting on others)

- Ionut: review of `feat/w4-contract` (0.8.0-draft: `reason`, `GET /seasons`, `event_id` required, WS 401 on a bad token) and `feat/w4-realtime`; deploy of the WS hub, `game_event`, `GET /me/events`, `POST /landing-scans` and contract 0.8.0; the landing sticker token format and printed stickers; the per-scan points value (15.3 accessible mode); agreement on "no third person for the pilot".
- Server: every probe to `api.floorwars.me` timed out from this laptop on 2026-11-17 (`/healthz`, `/v1/me/events`, `/v1/landing-scans`, `/v1/seasons`, `/v1/me/segments`, `/v1/ws`). Cause unknown (VM firewall allows team IPs only).
- No `impeccable` plugin on this project: screens were built with the `parts.tsx` look (Cristea's decision); a design pass needs the plugin.

### Notes the agents found

- `MainActivity.onNewIntent` now calls `setIntent(intent)` (`16d421f`): without it a notification tap after Android killed the process opened Home instead of Standings. No unit test (ReactActivity does not load under Robolectric); emulator only.
- Realtime build changes: `testOptions.unitTests.includeAndroidResources = true`; `src/test/resources/robolectric.properties` with `application=android.app.Application`; a debug-only `DebugGameEventReceiver` posts test events through the real pipeline.
- `DEV_FORCE_NO_BAROMETER` is committed `false`; set it `true` locally for the click-through only.

You are implementing Cristea's part of Week 4 in `D:\FloorWars`. Work in one session, on feature branches from `main`. Follow the checklist in section 3 in order, except where a step says it can run in parallel. Tick each box only after its verification command has run and passed.

Goal from the plan: *the loop is visible and social.*

Exit from the plan: *two phones on different teams: phone 1 climbs, phone 2's building standings flip live and phone 2 gets a notification. The barometer-less path works on a device or an emulator flag.*

## 0. Ground rules

- **Cristea takes every decision. You may not guess.** If this prompt, the plan, the contract, a recorded answer from Cristea or the existing code does not settle a choice, stop that item and ask Cristea with `Skill("grilling")` (the grill-me skill). Your recommendation goes with the question, and nothing uses it until Cristea answers. Look up facts yourself. Carry on with items that do not depend on the answer.
- **This prompt follows `IMPLEMENTATION_PLAN.md`.** If you find a difference between them, or between the plan and the contract, stop that item and ask Cristea. An answer that changes the plan goes into the plan in the same PR (docs rule, section 9.3).
- **Read only the docs in section 2.** Do not read the rest of `IMPLEMENTATION_PLAN.md`, Ionut's `/server` source code, or the plan for later weeks. The server is described by the contract and `server/README.md`; that is enough. If you need something outside the list, say which file and why before opening it.
- Codebase questions: `graphify-out/` exists, so run `graphify query "<question>" --budget 1500` (or `graphify path`, `graphify explain`) before reading files. Read files only for the lines you need.
- Contract first. Do not edit `contracts/openapi.yaml`, except in W4-0's contract commit, which Cristea decided and Ionut reviews. Any other contract change is a PR reviewed by Ionut. If the contract blocks you, write the question under "Blocked" in section 4 and go on with other items.
- Do not edit `app/src/api/schema.ts` by hand. Regenerate it with `npm run generate:api` in `app/`.
- Do not install a new dependency without Cristea's approval. Name the candidates, their licence and last release date, and wait for the answer. Approved by Cristea (2026-11-17):
  - `react-native-svg`, runtime, W4-2. Pin the newest 15.x that is at least 14 days old on the day you install it (15.16.1 was released 2026-11-05, so it qualifies from 2026-11-19).
  - `react-native-reanimated` 4.7.1, runtime, W4-2 (released 2026-10-02, MIT, supports RN 0.86 to 0.88).
  - `react-native-worklets` 0.13.1, runtime, W4-2, the required peer of Reanimated 4.7 (released 2026-10-26, MIT).
  - `com.squareup.okhttp3:okhttp`, runtime, W4-1, declared explicitly at the version React Native already resolves (RN's version catalog names 4.9.2; confirm with `./gradlew :app:dependencies`).
  - `com.squareup.okhttp3:mockwebserver`, `testImplementation` only, W4-1, same version as `okhttp`.
  - Not approved: `@react-navigation/bottom-tabs`, `@react-native-async-storage/async-storage`.
- Do not commit real sensor recordings without reading their header (`docs/trace_format.md`). The W4-6 traces are Cristea's, real and labelled; check each header before the commit.
- Do not log or store coordinates, and do not send anything beyond what the contract asks for (plan section 8, data minimisation). Notifications carry the team code and the building only.
- Branches, one PR each into `main`, merged with "Create a merge commit" (not squash, not rebase), in this order:
  1. `feat/w4-contract` (W4-0 contract commit), from `main`. Ionut reviews.
  2. `feat/w4-seam` (W4-0 seam commit), from `main`.
  3. `feat/w4-realtime` (W4-1), from `feat/w4-seam`. Ionut reviews.
  4. `feat/w4-screens` (W4-2, W4-3), from `feat/w4-seam`.
  5. `feat/w4-fallback` (W4-4, W4-5), from `feat/w4-seam`.
  6. `feat/w4-tuning` (W4-6), from `main`.
  7. `docs/w4-finish` (W4-8 docs), from `main` after the others merge.
  Do not run `git checkout` on `main` in a way that loses uncommitted work.
- **Server state, checked 2026-11-17:** `https://api.floorwars.me` did not answer from this laptop (TCP connect to `4.223.83.29:443` timed out after 10 s on `/healthz`, `/openapi.json` and every `/v1` path tried; DNS resolves). The README says the VM firewall allows team IPs only, so this may be the laptop's network, not the server. `origin/main` has no Week 4 server work: no WebSocket hub, no `game_event`, no `GET /v1/me/events`, no `POST /v1/landing-scans`, no landmarks. All Week 4 app work is built and tested against the Prism mock (`npm run mock:api`, port 4010), Jest fakes and OkHttp's `MockWebServer` (Cristea's decision, 2026-11-17). Prism cannot serve a WebSocket. The switch to the real server is one item in W4-8, after Ionut deploys his Week 4 work and the contract PR.
- Before you claim any item done, run its verification command and paste the summary line into your report. No claim without output.
- If a root cause is unclear for a failing test, find the cause first, then fix. Do not patch around a symptom.

## 1. Current state (checked 2026-11-17)

- **Week 3:** all Week 3 PRs are merged into `main` (#62 to #68, #70, #71, #72). `main` is at `525f002` ("docs: mark Week 3 finished, add the tester guide PDF"), clean, level with `origin/main`. `cristea/week_3/finish_week_3.md` has every box ticked, but the "Week 3 service survival" table in `docs/devices.md` still reads `pending` in all 8 rows. Cristea ran those rows and will paste the numbers (W4-7).
- **Ionut, Week 4:** nothing on `origin/main` after 2026-11-08 from his side. The README row "Backend, week 3" still says "Not yet deployed" (out of date: `finish_week_3.md` step 2 records the deploy of `fbe9c18` on 2026-11-08).
- **Contract:** `contracts/openapi.yaml` is 0.7.0-draft. Paths this week reads: `GET /buildings`, `GET /buildings/{id}/standings` (`BuildingStandings`, `TeamStanding`), `GET /leaderboards` (`Leaderboard`, `LeaderboardEntry`; `scope` individual, team or building; `building_id` required for building; `limit` 1 to 100, default 50), `GET /me/segments` (`SegmentPage`, `SegmentRecord`, cursor pages), `GET /me/events` (`GameEventPage`), `GET /me/season-stats` (`SeasonStats`), `GET /teams`, `GET /seasons/active`, `POST /landing-scans` (`LandingScanRequest`, `LandingScan`; 201, 403, 422, 429), `WS /ws` (`since`, `access_token` query or bearer header; `WsEvent` = `BuildingFlippedEvent` or `SeasonStateEvent`, both with `event_id`).
- **Contract gaps found 2026-11-17:** `SegmentRecord` has no rejection reason, so the history screen cannot show one. There is no list of seasons (only `GET /seasons/active`), so the season selector has nothing to read. W4-0 fixes both in contract 0.8.0-draft.
- **What exists that this week builds on (reuse, do not duplicate):**
  - `app/src/native/NativeFloorSensors.ts`: the TurboModule spec with `getStatus` (carries `has_barometer`), `setActiveCheckin`, `getActiveCheckin`, `getPendingCount`, the event emitters `onStatusChange` and `onPendingChanged`, and the battery-optimisation methods.
  - `FloorSensorsModule.kt`, `FloorSensorsService.kt` (foreground service, notification channel, check-in driven sensors and wake lock), `ActiveCheckinStore.kt`.
  - `app/src/sync/syncWorker.ts`, `app/src/sync/triggers.ts` (`backgroundSyncTask`, the Headless JS task `FloorWarsSync` registered in `app/index.js`), `com/floorwars/sync/SyncWorker.kt` and `SyncTaskService.kt` (15-minute WorkManager job). The worker passes flips from `POST /segments` to a callback with no UI yet.
  - `app/src/auth/session.ts`: Keychain tokens, `getAccessToken`, the team flag (`markTeamChosen(seasonId)`, `getChosenSeason`), `getDeviceId`, `endSession`. The app stores the joined season id, not the team id or code.
  - `app/src/api/client.ts`: generated client, token refresh, 10 s and 20 s timeouts, and `API_BASE_URL`.
  - `app/src/screens/HomeScreen.tsx` (titled "Status"), `homeStatus.ts`, `CheckinScreen.tsx` (QR scan through `react-native-vision-camera` and the barcode scanner, location check-in, the camera-permission message), `app/src/checkin/qr.ts` (entrance tokens only: `fwq1.<payload>.<hmac>`, at most 512 characters).
  - `app/src/scoring/floorEquivalent.ts`: 20 verified steps = 1 floor-equivalent, labelled "floors (estimate)".
  - `app/src/navigation/RootNavigator.tsx`: native stack, Auth stack (Email, Otp, Team) and Main stack (Home, Checkin, SensorLogger). No linking config.
  - `app/src/config/devFlags.ts`: `DEV_SKIP_SIGN_IN`.
  - `app/src/ui/parts.tsx`: the shared look.
- **What does not exist yet:** any WebSocket code (W4-1), a local notification for game events (W4-1), deep links (W4-1), the standings, leaderboards, history and onboarding screens (W4-2, W4-3, W4-5), the landing-scan flow (W4-4), today's figures on Home (W4-3).
- **Real measurements to respect:** access tokens live 900 s (`server/app/config.py`, `access_token_ttl_s`); refresh tokens rotate with reuse detection, so only one place may refresh (JS). Pressure arrives at about 25 Hz (SM-S918B) or 10 Hz (SM-G985F). Real stairs gave 4.3 to 8.7 steps per metre.
- **Installed (app):** React Native 0.88.0, React 19.3.0, `@react-navigation/native` 7.5.1 and `native-stack` 7.21.0, `react-native-vision-camera` 5.2.4 with the barcode scanner, `react-native-keychain` 10.0.0, `@react-native-community/geolocation` 3.4.0, `@testing-library/react-native` 14.1.0, Jest 29.7.0, `openapi-typescript` 7.13.0. Android: Room 2.8.5 (KSP), WorkManager 2.12.0, JUnit 4.13.2, Robolectric 4.17 (tests). Not installed: `react-native-svg`, Reanimated, worklets.
- **CI:** `.github/workflows/app.yml` with jobs "android unit tests and trace replay" (`./gradlew ktlintCheck test`, including the `TraceReplayTest.realTraces` gate, `MIN_STAIRS_PRECISION = 0.9`) and "lint, typecheck, test, API client". Both must stay green.
- **Test devices:** SM-S918B and SM-G985F, both with a barometer. `traces/` holds 21 real CSV traces plus `labels.csv` (stairs_up 3, stairs_down 4, elevator_up 2, walk_flat 6, shake 3, blow 3); `fixtures/synthetic/` holds the 24 synthetic traces and their tools.
- **Carried over from Week 3:** writing the survival numbers into `docs/devices.md` (W4-7). The other open points of `finish_week_3.md` ("Open after Week 3") stay out of Week 4 unless a Week 4 phone check fails (Cristea's decision, 2026-11-17).

## 2. Documents to read (and only these)

| Doc | Which part | Needed for |
|---|---|---|
| `IMPLEMENTATION_PLAN.md` | Section 10, "Week 4" (Cristea and exit lines only) | All |
| `IMPLEMENTATION_PLAN.md` | Section 9.2 (working rules) and 9.3 (Week 4 row) | W4-8 |
| `.github/workflows/app.yml` | Whole file | All (CI must stay green) |
| `IMPLEMENTATION_PLAN.md` | Section 7.2.1 (notifications without Firebase) | W4-0, W4-1 |
| `IMPLEMENTATION_PLAN.md` | Section 7.10 (network-failure strategy) | W4-1, W4-2, W4-3, W4-4 |
| `IMPLEMENTATION_PLAN.md` | Section 2 (game rules), section 8 (security and privacy) | W4-2, W4-3, W4-4, W4-5 |
| `IMPLEMENTATION_PLAN.md` | Section 3.3 (sensor fusion and starting thresholds) | W4-6 |
| `contracts/openapi.yaml` | The paths and schemas listed in section 1, plus `Problem`, `Season`, `Team`, `Building`, `RejectedSegment`, `BuildingFlip` | W4-0 to W4-4 |
| `contracts/prism/README.md` | Whole file | W4-2 to W4-5 |
| `server/README.md` | Sections on auth, segments, leaderboards and WebSocket if present | W4-1, W4-8 |
| `docs/evaluation.md`, `docs/trace_format.md` | Whole files | W4-6 |
| `docs/devices.md` | Section "Week 3 service survival" | W4-7 |
| Code | The files named in section 1 under "What exists", only the lines you need | All |

Do not read earlier weeks' files in `cristea/` in full. W4-7 needs only `cristea/week_3/finish_week_3.md`, step 4.

## 3. Checklist

### Plan coverage

| Plan line (section 10, Week 4; section 9.3) | Item |
|---|---|
| WebSocket connection manager (auth, reconnect, resume) exposed as a hook for the game screens | W4-0 (seam), W4-1 |
| Building standings screen (`react-native-svg`): team shares in team colours from `GET /v1/buildings/{id}/standings`, live updates from `building_flipped`, Reanimated colour-flip animation | W4-2 |
| Leaderboards screen: individual, team, building tabs; season selector | W4-0 (contract `GET /seasons`), W4-2 |
| Home screen: current check-in, today's stair steps and metres, pending-sync indicator | W4-3 |
| Personal history screen with the reason for each rejected segment | W4-0 (contract `reason`), W4-3 |
| Barometer-less fallback: detect `has_barometer=false`, QR-sticker-on-landing flow ("scan at the stairs of building X") with local rate limit | W4-4 |
| Onboarding: safety copy (no running), permission explanations, per-manufacturer battery-optimisation guide | W4-5 |
| Classifier tuning pass 1 with new real-world traces (pocket, bag, hand, going down, flat walking). Record new precision and recall. | W4-6 |
| Ionut line, paired: socket in the Kotlin service, the local notification and the tap that deep-links to the building screen | W4-1 |
| 9.3, Week 4: Notifications, Pair, done when phone 2 gets a notification when phone 1 flips a building | W4-8 |
| 15.3: Accessible contribution mode rules (Both, Week 4) | W4-4 (app side), W4-8 (record) |
| 15.3: Third person for the pilot logistics (Both, Week 4) | W4-8 (record) |
| Carried over from Week 3: survival table in `docs/devices.md` | W4-7 |
| Exit line | W4-8 |

Dependencies: W4-0 first. Then W4-1, W4-2 with W4-3, and W4-4 with W4-5 run in parallel in their own worktrees. W4-2's live update uses the hook from the seam, so it builds against the seam's fake and does not wait for W4-1. W4-6 waits for Cristea's 20 traces, and is independent of the other tracks. W4-7 waits for Cristea's numbers. W4-8 last.

The seam (this session commits it on `feat/w4-seam` in W4-0, so every agent builds against it from its first commit). Owners: `w4-realtime` implements the native side and the hook; the other agents only call them.

```ts
// app/src/native/NativeFloorSensors.ts, added to Spec (TurboModule codegen has no unions, so events cross as JSON)
export type GameEventJson = { json: string };            // one WsEvent from contracts/openapi.yaml, as JSON text
export type RealtimeState = { state: string };           // 'connecting' | 'open' | 'closed' | 'auth_needed'

  // w4-realtime
  configureRealtime(wsUrl: string, accessToken: string | null): void; // JS calls after sign-in, every token refresh, app foreground and every headless sync run
  setRealtimeContext(myTeamCode: string | null, buildingNamesJson: string): void; // team code of the joined season; [{id,name}] from GET /buildings
  startRealtime(): void;  // the app is in the foreground: hold the socket
  stopRealtime(): void;   // the app left the foreground: release the foreground hold
  deliverPolledEvents(pageJson: string): void; // a GameEventPage from GET /me/events, run through the same pipeline as socket events
  getLastEventId(): Promise<number>;
  clearRealtime(): void;  // sign-out: close the socket, forget token, team, names and the last event id
  readonly onGameEvent: CodegenTypes.EventEmitter<GameEventJson>;
  readonly onRealtimeState: CodegenTypes.EventEmitter<RealtimeState>;
```

```ts
// app/src/realtime/useGameEvents.ts (the hook the game screens use)
import type { components } from '../api/schema';
export type WsEvent = components['schemas']['WsEvent'];
export type RealtimeStatus = 'connecting' | 'open' | 'closed' | 'auth_needed';
export function useGameEvents(onEvent: (e: WsEvent) => void): { status: RealtimeStatus };
```

The seam commit holds: the Spec additions above, Kotlin overrides in `FloorSensorsModule.kt` that do nothing and resolve `0`, and `useGameEvents` returning `{ status: 'closed' }` and never calling `onEvent`, plus a Jest fake of the native module with the new methods. `w4-realtime` replaces the bodies, not the signatures. Any change to a signature is a question for Cristea.

### 3.1 Subagents and worktrees

The work is delegated to project subagents in `.claude/agents/`. Each one owns the checklist items below. This session coordinates: it starts the agents with the Agent tool, puts their questions to Cristea, runs the checks, commits the contract and the seam, and does W4-7 and W4-8. It does not implement the delegated items itself.

| Agent | Items | Worktree | Model, effort |
|---|---|---|---|
| `w4-preflight` | W4-0 (all but the contract and the seam) | main checkout | haiku, low |
| `w4-realtime` | W4-1 | `D:/FloorWars-w4/realtime` | opus, high |
| `w4-screens` | W4-2, W4-3 | `D:/FloorWars-w4/screens` | sonnet, medium |
| `w4-fallback` | W4-4, W4-5 | `D:/FloorWars-w4/fallback` | sonnet, medium |
| `w4-tuning` | W4-6 | `D:/FloorWars-w4/tuning` | opus, high |

Order:

1. Start `w4-preflight` first. Wait for its report.
2. This session commits the contract on `feat/w4-contract` and the seam on `feat/w4-seam`, runs both verify commands on each, then creates the realtime, screens and fallback worktrees from `feat/w4-seam` and the tuning worktree from `main`.
3. `w4-realtime`, `w4-screens` and `w4-fallback` run in parallel, each in its own worktree. `w4-screens` does W4-2, then W4-3. `w4-fallback` does W4-4, then W4-5. `w4-tuning` starts only after Cristea's 20 traces are committed on its branch.
4. W4-7, W4-8 and the phone checks are done in this session, after all agents report.

Rules for this session:

- Start each agent with the Agent tool. Give it the item IDs and its worktree path in the prompt. Its own `.claude/agents/<name>.md` holds its scope, documents and rules.
- Re-run each item's verify command yourself, forced and not cached (`./gradlew test --rerun-tasks`, `npx jest --no-cache`), before you tick its box, and check that the tests fail when the rule they guard is broken. Agent reports are evidence, not proof.
- Agents cannot ask Cristea. When an agent lists a Blocked question, ask Cristea with `Skill("grilling")`, record the answer in section 4, and send it back to the agent. The other items carry on meanwhile.
- Worktrees need the project skills and agents copied in, because `.claude/` is gitignored. They also need `npm ci` in `app/`, because `node_modules` is not shared and the Android build reads it too.
- UI items (W4-2, W4-3, W4-4, W4-5) are built with the existing `app/src/ui/parts.tsx` look, without the impeccable skills: the plugin is not installed for this project (Cristea's decision, 2026-11-17, replacing the earlier rule that required them).
- Files that two agents both edit: `RootNavigator.tsx` (realtime adds the linking config, screens adds Standings, Leaderboards and History, fallback adds LandingScan and Onboarding) and `HomeScreen.tsx` (screens adds today's figures and the buttons, fallback adds the landing-scan entry and "How it works"). Merge order realtime, screens, fallback: the later branch rebases on the earlier one and resolves the conflict. `package.json` and `package-lock.json`: only `w4-screens` adds npm packages.
- If the Agent tool does not list these agents, restart the session. Project agents load when a session starts. The Week 3 agents were removed (Cristea's decision, 2026-11-17).
- Section 2 applies to the agents too. They read only the documents their agent file names.

Commands (also the reference for the paths):

```
# this session, W4-0:
git worktree add D:/FloorWars-w4/contract -b feat/w4-contract main
git worktree add D:/FloorWars-w4/seam     -b feat/w4-seam     main
# after the seam commit:
git worktree add D:/FloorWars-w4/realtime -b feat/w4-realtime feat/w4-seam
git worktree add D:/FloorWars-w4/screens  -b feat/w4-screens  feat/w4-seam
git worktree add D:/FloorWars-w4/fallback -b feat/w4-fallback feat/w4-seam
git worktree add D:/FloorWars-w4/tuning   -b feat/w4-tuning   main
# for each worktree:
mkdir -p <worktree>/.claude && cp -r D:/FloorWars/.claude/skills D:/FloorWars/.claude/agents D:/FloorWars/.claude/settings.json <worktree>/.claude/
cd <worktree>/app && npm ci
```

Do not run `git checkout` in `D:\FloorWars`. Check `git worktree list` after each addition.

### W4-0 Preflight, contract and seam (first)

*Delegate: `w4-preflight`, except the contract and the seam, which this session commits.*

- [ ] `git status` and `git branch --show-current`. Confirm `main` is up to date with `origin/main`. List any local changes; do not touch them.
- [ ] Baseline, before any change, and record the summary lines: `cd app/android && ./gradlew test ktlintCheck` and `cd app && npm run lint && npm run typecheck && npm test`.
- [ ] `curl.exe -i https://api.floorwars.me/healthz`, and check which of these answer something other than 404 without a token: `GET /v1/me/events`, `POST /v1/landing-scans`, `GET /v1/seasons`, `GET /v1/me/segments`, `GET /v1/ws`. Record the answers with the date. A timeout is recorded as a timeout, not as "not deployed".
- [ ] This session, contract commit on `feat/w4-contract` (Cristea's decision, 2026-11-17), version 0.8.0-draft with a changelog line:
  - a new schema `RejectionReason` holding the 14 reasons of `RejectedSegment.reason` today; `RejectedSegment.reason` refers to it;
  - `SegmentRecord` gains `reason`, type `RejectionReason` or `null`, required, `null` unless `status` is `rejected`;
  - `GET /seasons` (operationId `listSeasons`), 200 with an array of `Season`, newest `starts_at` first, 401 `Unauthorized`.
  Then `npm run generate:api`, the contract tests, and commit `schema.ts` with it.
- [ ] This session, seam commit on `feat/w4-seam`: the code of section 3 "The seam". Run both verify commands on it. Then create the other worktrees (section 3.1).
- Verify: `cd app && npm run generate:api && npx jest __tests__/apiContract` on `feat/w4-contract`; both full verify commands on `feat/w4-seam`.
- Done when: both baselines are recorded, the server state is known, the contract commit passes the contract tests, the seam is green, and all worktrees exist. Pre-existing failures are listed, not fixed silently.

### W4-1 Realtime: socket, hook, notification, deep link, fallback poll (Kotlin and TypeScript)

*Delegate: `w4-realtime` (worktree `D:/FloorWars-w4/realtime`).*

- [ ] One socket, owned by Kotlin (Cristea's decision, 2026-11-17). A process-wide `RealtimeClient` in `com/floorwars/realtime/` on OkHttp's WebSocket. It is open while at least one holder holds it: the foreground holder (`startRealtime` / `stopRealtime`, called by JS on AppState changes) and the session holder (`FloorSensorsService` while a check-in is active). It closes when neither holds it, and on `clearRealtime()`.
- [ ] Connect to `<wsUrl>?since=<lastEventId>` with the token as `Authorization: Bearer <token>` (the contract's bearer scheme; the token stays out of the URL). `wsUrl` is `API_BASE_URL` with `https` replaced by `wss`, plus `/ws`.
- [ ] Auth (Cristea's decision, 2026-11-17): native never refreshes. JS hands the access token over with `configureRealtime` after sign-in, after every refresh in `client.ts`, on app foreground and in every headless sync run. Native keeps it in memory only. A 401 on the upgrade, or a close for auth, sets state `auth_needed` and stops reconnecting until `configureRealtime` brings a new token.
- [ ] Timing (Cristea's decision, 2026-11-17): ping every 30 s (`PING_INTERVAL_S = 30`). Reconnect with exponential backoff and full jitter: `RECONNECT_BASE_MS = 1_000`, doubling, `RECONNECT_CAP_MS = 60_000`; the attempt counter resets after a connection stays open `RECONNECT_RESET_AFTER_MS = 60_000`. Use an injectable clock and random source.
- [ ] One event pipeline in Kotlin (`GameEventPipeline`, pure Kotlin, no Android imports), used by the socket and by `deliverPolledEvents`: parse each `WsEvent`, drop an `event_id` at or below the last handled id, store the new last id in `SharedPreferences` (`KEY_LAST_EVENT_ID`), emit `onGameEvent` to JS when the module is alive, and pass it to the notifier. An unknown `type` is skipped and still advances the id.
- [ ] Notifier (Cristea's decision, 2026-11-17): post a local notification only for `building_flipped` where `from_team` equals the player's team code (`setRealtimeContext`); never for `season_state`, never for a win. At most one notification per building per 10 minutes on the phone (`NOTIFY_MIN_INTERVAL_MS = 600_000`, timestamps per building in `SharedPreferences`). A new notification channel `game_events`, name "Building alerts". Text (Cristea approved it in this prompt, 2026-11-17; copy it exactly):
  - title: `{to_team} took {building name}`; when the name is unknown: `{to_team} took building {building_id}`
  - text: `Your team lost it. Tap to see the standings.`
- [ ] Deep link (Cristea's decision, 2026-11-17): the notification opens `floorwars://building/{building_id}`. Add the intent filter (scheme `floorwars`, host `building`) on `MainActivity` in `AndroidManifest.xml`, and the React Navigation `linking` config (`prefixes: ['floorwars://']`, `Standings: 'building/:buildingId'`) in `RootNavigator.tsx`. It works from a cold start and a warm app. When the Auth stack is showing, the link is dropped.
- [ ] JS side, `app/src/realtime/`: `useGameEvents` subscribes to `onGameEvent` and `onRealtimeState`, parses the JSON into `WsEvent`, and unsubscribes on unmount. An `AppState` listener calls `startRealtime` / `stopRealtime`. After sign-in and on app start with a session, JS loads the team code (`GET /me/season-stats` gives `team_id`, `GET /teams` maps it to `code`) and the names (`GET /buildings`) and calls `setRealtimeContext`. `endSession()` calls `clearRealtime()`.
- [ ] Fallback poll (Cristea's decision, 2026-11-17): `backgroundSyncTask` in `app/src/sync/triggers.ts` also calls `GET /me/events?since=<getLastEventId()>&limit=100`, hands each page to `deliverPolledEvents`, and repeats while `has_more` is true, at most 5 pages per run (`MAX_EVENT_PAGES = 5`). It runs after the segment sync and its failure never fails the sync. No new WorkManager job.
- [ ] Tests, JUnit with `MockWebServer`: connects with the bearer header and `since`; replay then live events; a duplicate `event_id` is dropped; an id at or below the stored one is dropped after a process restart (new pipeline, same preferences); reconnect delays follow the backoff with a fixed random source and reset after 60 s open; 401 stops reconnecting until a new token; the socket closes when both holders release; ping interval set to 30 s. Notifier: loss notifies, win does not, `season_state` does not, a second loss in the same building within 10 minutes does not, the same after 10 minutes does; unknown name uses the fallback title. Jest: the hook parses events, reports state, unsubscribes; the poll pages until `has_more` is false or 5 pages; a poll failure leaves the sync result unchanged; `endSession` calls `clearRealtime`.
- Verify: `cd app/android && ./gradlew test ktlintCheck` and `cd app && npm run lint && npm run typecheck && npm test`. Paste the summary lines.
- Done when: the tests pass, and they fail if the duplicate-drop or the 10-minute limit is removed (break each once, check, revert). On the emulator: a notification posted through a debug-only test hook, tapped, opens the Standings screen of that building, cold and warm, recorded in the PR description. The live socket against the real server is W4-8.

### W4-2 Building standings and leaderboards (React Native)

*Delegate: `w4-screens` (worktree `D:/FloorWars-w4/screens`).*

- [ ] Install `react-native-svg` (pinned as in section 0), `react-native-reanimated` 4.7.1 and `react-native-worklets` 0.13.1, with the Babel plugin Reanimated 4 requires. Report each version, licence and release date. Android build and Jest must both still run.
- [ ] Standings screen, route `Standings` with param `buildingId` (the deep-link target of W4-1). Data from `GET /buildings/{id}/standings`. Layout (Cristea's decision, 2026-11-17): the building name and the owner on top (`Owned by {code}` or `Nobody owns this building yet`), one horizontal bar in SVG split into each team's share of the points in its `color_hex`, then a list of teams with code and points, most points first. Points, not floors; no floor-equivalent here.
- [ ] Live update: `useGameEvents`. On a `building_flipped` for this building, the owner's colour animates from the old team's colour to the new one over `FLIP_ANIMATION_MS = 600` with Reanimated, then the screen refetches the standings. Events for other buildings are ignored.
- [ ] Leaderboards screen, route `Leaderboards`: three tabs inside the screen (individual, team, building), `GET /leaderboards` with `limit=50`. Season selector from `GET /seasons` (W4-0), defaulting to the active season. Until `GET /seasons` is deployed, the selector shows only the active season (from `GET /seasons/active`) and is listed under Blocked. Building tab: a building picker from `GET /buildings`, defaulting to the active check-in's building, else the first building by name (Cristea's decision, 2026-11-17).
- [ ] Reached from buttons on Home (no tab bar, Cristea's decision, 2026-11-17): "Leaderboards", and "Building standings" (the active check-in's building; hidden with no check-in).
- [ ] Reads are cached in memory per key (Cristea's decision, 2026-11-17): when a refresh fails and a cached copy exists, show it with `Last updated {HH:MM}. Can't reach the server.` Lost on app restart.
- [ ] States, wording (Cristea approved it in this prompt, 2026-11-17):
  - loading: a spinner, no text
  - standings empty: `No team has points here in the last 7 days. Climb the stairs to claim it.`
  - leaderboard empty: `No points on this board yet this season.`
  - offline with no cache: `Can't reach the server. Check your connection, then pull down to retry.`
  - 404 building: `This building doesn't exist anymore.`
  - other error: `Something went wrong loading this. Pull down to retry.`
- [ ] Tests (RNTL): bar segment widths match the shares; owner and no-owner headings; a flip for this building triggers the animation and a refetch, a flip for another building does not; leaderboard tab switching sends the right `scope` and `building_id`; season selector default; building picker default with and without a check-in; each state above; the cached copy with its label.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`, and `cd app/android && ./gradlew test ktlintCheck` (the native packages must not break the Android build). Paste the summary lines.
- Done when: the tests pass, and the screens were clicked through on the emulator against the Prism mock, recorded element by element in the PR description.

### W4-3 Home today figures and personal history (React Native)

*Delegate: `w4-screens` (worktree `D:/FloorWars-w4/screens`).*

- [ ] Home keeps the current check-in and the pending count (`getPendingCount()`, `onPendingChanged`) it already shows. It adds today's figures (Cristea's decision, 2026-11-17): the sum of `steps_scored` and of `ascent_m` over `verified` items of `GET /me/segments` with `started_at` at or after the phone's local midnight, paging with `next_cursor` until an item is older than midnight. Shown as `Verified today: {steps} steps, {metres} m` with metres to one decimal. Pending climbs are not counted here.
- [ ] History screen, route `History`, reached from a "Climb history" button on Home. `GET /me/segments`, 50 per page, newest first, next page loaded at the end of the list (Cristea's decision, 2026-11-17). Each row: date and time, building name (from `GET /buildings`, else `Building {id}`), steps, ascent in metres, status, and for `verified` the `steps_scored`.
- [ ] Rejected rows show the reason in words (Cristea approved it in this prompt, 2026-11-17; copy it exactly; never shame elevator use):
  - `pressure_steps_mismatch`: `Your steps and the height you climbed didn't match, so it didn't count as stairs.`
  - `ascent_range`: `The climb was under 2 m or over 120 m.`
  - `steps_range`: `The step count was outside what one climb can have.`
  - `speed`: `The height changed faster or slower than walking up stairs.`
  - `cadence`: `Your steps came faster or slower than walking pace.`
  - `duration`: `The climb was too short or too long to count.`
  - `rate_limit`: `You reached the limit of counted steps for now. Later climbs count again.`
  - `no_checkin`: `You weren't checked in when you climbed. Check in at the building first.`
  - `building_mismatch`: `The climb didn't match the building you checked in at.`
  - `started_at_range`: `The climb's time is more than 7 days old or in the future. Check your phone's clock.`
  - `season_inactive`: `No season was running when you climbed.`
  - `no_team`: `You hadn't joined a team this season when you climbed.`
  - `stair_prob_range`: `The app sent a value the server didn't accept. That's an app bug, not you.`
  - `overlap`: `This climb overlaps one that already counted, so it counted once.`
  - any other string: `Not counted (reason: {reason}).`
  - `reason` missing (contract 0.8.0 not deployed yet): `Not counted.`
- [ ] States (same rules as W4-2): history empty `No climbs yet. Check in at a building and take the stairs.`; today's figures while loading show `Verified today: loading`; when they cannot load, `Verified today: unavailable` and the cached value with its `Last updated` label if one exists.
- [ ] Tests (RNTL and plain Jest): local-midnight boundary (a climb at 23:59 yesterday is excluded, 00:00 today included), paging stops at the first older item, only `verified` counts, metres rounding; every reason string above, the unknown reason and the missing reason; paging at the list end; each state.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`. Paste the summary lines.
- Done when: the tests pass, the tests fail if pending or rejected rows are counted in today's figures (break once, check, revert), and Home and History were clicked through on the emulator against the Prism mock, recorded element by element in the PR description.

### W4-4 Barometer-less fallback (React Native)

*Delegate: `w4-fallback` (worktree `D:/FloorWars-w4/fallback`).*

- [ ] Detect `has_barometer` from `getStatus()`. `DEV_FORCE_NO_BAROMETER` in `app/src/config/devFlags.ts` forces it to `false` in `__DEV__` builds only; release builds ignore it (Cristea's decision, 2026-11-17).
- [ ] When `has_barometer` is false, Home shows a "Scan at the stairs" button instead of the detection rows. It opens route `LandingScan`, which reuses the camera scanner and permission handling of `CheckinScreen.tsx` (no second copy).
- [ ] Building and check-in (Cristea's decision, 2026-11-17): a scan needs an active check-in; `building_id` is the check-in's building. The app sends the scanned text as `qr_token` unchanged, after only these checks: at most 512 characters, no control characters. The sticker format is Ionut's and is not defined yet (Blocked); the app does not parse it. `scanned_at` is the phone time in ISO 8601.
- [ ] Local rate limit (Cristea's decision, 2026-11-17): after a 201, scanning in that building is disabled for `LANDING_SCAN_COOLDOWN_MS = 600_000`, kept in memory per building. A 429 honours `Retry-After` the same way.
- [ ] Points (Cristea's position for the 15.3 decision, 2026-11-17): the app shows the `points` the server returns and computes none. The per-scan value is Ionut's server setting.
- [ ] Wording (Cristea approved it in this prompt, 2026-11-17; copy it exactly):
  - heading: `Scan at the stairs of {building name}`
  - body: `Your phone has no barometer, so it can't measure climbs. Scan the sticker on a stair landing instead.`
  - no check-in: `Check in at the building first, then scan the sticker on a stair landing.`
  - 201 with points: `Scan counted: +{points} points.`; without points: `Scan counted.`
  - cooldown: `You can scan again in this building in {n} min.`
  - 403: `This sticker isn't for this building, or it has expired.`
  - 429: `Too many scans. Try again in {n} min.`
  - 422 or a token that fails the local checks: `This code isn't a FloorWars stair sticker.`
  - offline: `Couldn't send the scan. Check your connection and try again.`
- [ ] Flips returned by the scan go to the same flip handling as `POST /segments` (no separate UI).
- [ ] Tests: the flag is ignored outside `__DEV__`; Home shows the scan entry only without a barometer; no scan without a check-in; the request body holds exactly `qr_token`, `building_id`, `scanned_at`; the token checks; the cooldown and `Retry-After`; each message above.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`. Paste the summary lines.
- Done when: the tests pass, the tests fail if the cooldown is removed (break once, check, revert), and the flow was clicked through on the emulator with `DEV_FORCE_NO_BAROMETER` against the Prism mock, recorded element by element in the PR description.

### W4-5 Onboarding (React Native)

*Delegate: `w4-fallback` (worktree `D:/FloorWars-w4/fallback`).*

- [ ] Route `Onboarding`, shown once after the team choice and before Home (Cristea's decision, 2026-11-17). The "seen" flag lives in the same Keychain store as the team flag in `session.ts` and is not cleared on sign-out. Home has a "How it works" button that opens it again. One scrolling screen, ending with the button `I've read this`.
- [ ] Wording (Cristea approved it in this prompt, 2026-11-17; copy it exactly):
  - Safety: `Walk, don't run. Points come from steps, never from speed: a slow climb scores the same as a fast one. Hold the handrail, and stop if you feel unwell. Taking the elevator is fine. It just doesn't score.`
  - Physical activity: `FloorWars counts your steps on stairs. Android calls this permission Physical activity. Without it, climbs aren't detected.`
  - Notifications: `Lets FloorWars show that it's detecting climbs while you're checked in, and tell you when another team takes your building.`
  - Camera: `Used only to scan the codes at building entrances and on stair landings. No photos are saved.`
  - Location: `Used once, when you check in by location, to find which building you're in. FloorWars doesn't track where you go.`
  - Battery, intro: `Android can stop FloorWars in the background to save battery, and then climbs go missing. Let it run:`
  - Samsung (`Platform.constants.Manufacturer` is `samsung`): `Settings > Apps > FloorWars > Battery > Unrestricted. Then Settings > Battery > Background usage limits, and make sure FloorWars isn't under Sleeping apps or Deep sleeping apps.`
  - Xiaomi, Redmi, POCO (`xiaomi`, `redmi`, `poco`): `Settings > Apps > Manage apps > FloorWars > Battery saver > No restrictions. On the same page, turn on Autostart.`
  - Any other manufacturer: `Settings > Apps > FloorWars > Battery, and choose Unrestricted or Don't optimise. The names differ between phones.`
  - Under the battery steps: the existing `openBatteryOptimizationSettings()` button, labelled `Open battery settings`.
- [ ] The onboarding asks for no permission itself; the existing flows still ask at the moment of use.
- [ ] Tests: shown once after the team choice, not again after a restart, not again after sign-out and sign-in; reopened from Home; the manufacturer picks the right section (case-insensitive), unknown falls back to the generic one.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`. Paste the summary lines.
- Done when: the tests pass and the screen was clicked through on the emulator, recorded element by element in the PR description. The Samsung steps are checked on both phones in W4-8.

### W4-6 Classifier tuning pass 1 (Kotlin, needs Cristea's traces)

*Delegate: `w4-tuning` (worktree `D:/FloorWars-w4/tuning`). Starts only after Cristea's traces are committed on `feat/w4-tuning`.*

- [ ] Cristea records 20 new real traces with the sensor logger screen (Cristea's decision, 2026-11-17), 10 per phone (SM-S918B, SM-G985F): `stairs_up` in `pocket` ×2, `bag` ×2, `hand` ×2; `stairs_down` in `pocket` ×2; `walk_flat` in `pocket` ×2. Each file and its `labels.csv` row follow `docs/trace_format.md`; this session reads each header before the commit. Cristea's check. Do not mark it done.
- [ ] Replay all traces in `traces/` and `fixtures/synthetic/` through `TraceReplayTest`, before any change, and record the confusion matrix and per-class precision and recall.
- [ ] Tune only the existing thresholds of the rules classifier (plan 3.3 table, `MAX_BLOW_WINDOW_S`, `MIN_SHAKE_FREE_ASCENT_M`) where a new trace is misclassified. No new feature, rule or model. Each change states the trace that motivated it. A change that makes any trace in the old set worse is not made.
- [ ] `MIN_STAIRS_PRECISION = 0.9` stays; the gate must stay green.
- [ ] A threshold that the server also checks (steps per metre 4 to 10, speed bounds) changes only on the phone side; a server change is a question for Ionut, listed under Blocked.
- [ ] Write the new matrix, per-class precision and recall, the per-label trace counts, and each threshold change with its reason into `docs/evaluation.md`, dated.
- Verify: `cd app/android && ./gradlew test ktlintCheck`. Paste the summary line and the matrix.
- Done when: the 20 traces are in `traces/`, the replay gate is green, `docs/evaluation.md` holds the before and after numbers, and the tests fail if a tuned threshold is reverted where the change fixed a trace (check once, revert).

### W4-7 Week 3 survival numbers (docs)

*Done in this session. Waits for Cristea's numbers.*

- [ ] Cristea pastes the 8 survival rows he ran in Week 3 (longest gap, gaps over 5 s, segment found, pending, battery used, per phone and state). Copy them into `docs/devices.md`, section "Week 3 service survival", replacing `pending`. If a row shows the service died, write it down and list it under Blocked with the fix `finish_week_3.md` names (`START_STICKY` with a restart from the stored check-in); do not build it without Cristea's decision.
- Verify: `grep -c pending docs/devices.md` drops by the number of cells filled.
- Done when: the 8 rows hold Cristea's numbers, on `docs/w4-finish`.

### W4-8 Integration and exit (last)

*Done in this session, not delegated. Runs after all tracks report.*

- [ ] Merge all branches into a local throwaway branch and run `cd app/android && ./gradlew test ktlintCheck` and `cd app && npm run lint && npm run typecheck && npm test` on it, so the tracks are proven together before any PR.
- [ ] Open one PR per branch into `main`, in this order: `feat/w4-contract`, `feat/w4-seam`, `feat/w4-realtime`, `feat/w4-screens`, `feat/w4-fallback`, `feat/w4-tuning`, `docs/w4-finish`. Rebase each on `main` after the previous one merges. Ask Ionut for review on `feat/w4-contract` and `feat/w4-realtime` (socket protocol, `/me/events` use) (Cristea's decision, 2026-11-17). Each PR says "tested against the Prism mock only" until the notification check below passes. CI must be green. `gh` is not installed: Cristea opens the PRs; give him the branch, title and body.
- [ ] Switch to the real server, once Ionut has deployed the WebSocket hub, `game_event`, `GET /me/events`, `POST /landing-scans` and contract 0.8.0: `curl.exe -i https://api.floorwars.me/healthz`, then the release APK from `main` on both phones. Write every surprise (field names, time zones, auth edges) in section 4.
- [ ] 9.3, Week 4 (Pair, Cristea and Ionut): phone 1 flips a building, and phone 2 gets a notification. Done when: phone 2 gets a notification when phone 1 flips a building. Run twice, once with phone 2's app open and once with it swiped away and no check-in (the 15-minute poll; note the delay). Cristea's check. Do not mark it done.
- [ ] Exit, on real phones (Cristea's checks, not claimed until he runs them; Cristea's decision, 2026-11-17):
  - SM-S918B joins team A, SM-G985F team B, both in the active season.
  - SM-G985F opens the Standings screen of the building.
  - SM-S918B checks in there and climbs until its team owns the building.
  - SM-G985F's owner colour flips live, without a refresh.
  - SM-G985F gets the notification `A took {building name}`, and tapping it opens that building's standings.
  - The barometer-less path: on the emulator with `DEV_FORCE_NO_BAROMETER` against the Prism mock, and once on a phone with a debug build and the flag on, against the real server once stickers exist.
  - The onboarding battery steps for Samsung are right on both phones.
- [ ] Record the two section 15.3 decisions in `IMPLEMENTATION_PLAN.md` once Ionut agrees: accessible mode (the app shows the server's `points`; Ionut sets the value), third person for the pilot (no, Cristea's position 2026-11-17).
- [ ] Update the README status row for Week 4, add this week's decisions to "Decisions taken", dated, and update `IMPLEMENTATION_PLAN.md` for anything that changed from it this week (docs rule, section 9.3). Write `cristea/week_4/week_4_summary.md` and `cristea/week_4/finish_week_4.md` with the manual steps.
- Done when: each PR's CI is green, every box above is ticked or listed as Cristea's or Ionut's, and the report lists the phone checks as Cristea's.

## 4. Report format

After each checklist item, post one line: `W4-n done | verify: <command> → <summary line> | commit: <sha>`. Agents post the same line in their reports. Copy them here after you have re-run the verify command. Keep these sections up to date in your final report:

- **Blocked:** items waiting on Cristea or Ionut, one line each: the question and your recommendation. Nothing uses a recommendation until Cristea answers. Expect at least: Ionut's review and deploy of contract 0.8.0 (`reason`, `GET /seasons`; W4-2, W4-3); Ionut's WebSocket hub, `game_event`, `GET /me/events` and `POST /landing-scans` deployed (W4-1, W4-4, W4-8); the landing sticker token format and printed stickers for both buildings (W4-4, W4-8); the per-scan points value, which settles the 15.3 accessible-mode row with Ionut (W4-4); Ionut's agreement on the third-person answer (W4-8); Cristea's 20 traces (W4-6); Cristea's survival numbers (W4-7); the server's view of the laptop timing out on 2026-11-17 (W4-0).
- **Decisions:** Cristea's answers only, one line each, with the date and the reason. Already decided (2026-11-17):
  - Week 3 survival rows were run; only the write-up carries over. The other Week 3 open points stay out unless a phone check fails.
  - `react-native-svg` (pinned 14 days old), Reanimated 4.7.1, worklets 0.13.1 approved; OkHttp explicit plus `mockwebserver` for tests approved; no bottom tabs, no AsyncStorage.
  - Native stack with buttons on Home, no tab bar.
  - One WebSocket, owned by Kotlin; JS hook subscribes through the module's event emitter.
  - JS hands the access token to native; native never refreshes; 401 waits for a new token.
  - Contract 0.8.0-draft written this week: `reason` on `SegmentRecord`, `GET /seasons`. Ionut reviews.
  - Home today figures: server, verified only, since local midnight.
  - Read cache in memory, with a "Last updated" label.
  - Build against Prism and fakes; switch to the real server in W4-8.
  - Accessible mode: the app shows the server's `points`; the value is Ionut's setting. Third person for the pilot: no.
  - Tuning pass 1: 20 traces, 2 per condition per phone.
  - Notification fallback poll in the existing sync job.
  - Notify only when the player's team loses a building, at most once per building per 10 minutes.
  - Deep link `floorwars://building/{id}`.
  - Standings as a stacked bar plus team list, 600 ms flip.
  - Landing scan uses the active check-in's building and sends the token unchanged; 10-minute local cooldown per building.
  - `DEV_FORCE_NO_BAROMETER` in `devFlags.ts`, debug builds only.
  - Onboarding once after the team choice, flag with the team flag, kept on sign-out, reopenable from Home.
  - Battery guide: Samsung, Xiaomi family, generic.
  - All user-facing wording is in this prompt, approved by Cristea; agents copy it exactly.
  - Agents and models as in section 3.1; branches and merge order as in section 0; Ionut reviews the contract and realtime PRs.
  - Backoff 1 s to 60 s, full jitter, reset after 60 s open, ping 30 s.
  - Leaderboards 50, season default active, building default from the check-in; history 50 per page.
  - Exit phone roles: SM-S918B climbs, SM-G985F watches.
  - The w3-* agents are removed once the w4-* agents exist.
  - 2026-11-17: `feat/w4-contract` is merged into `feat/w4-screens`, so the screens build on the 0.8.0 types (`GET /seasons`, `reason`); the PR order stays.
  - 2026-11-17: the UI agents build without the impeccable skills (not installed for this project), with the `parts.tsx` look.
  - 2026-11-17: onboarding section headings `Before you climb`, `Physical activity`, `Notifications`, `Camera`, `Location`, `Battery` approved; landing-scan screen loads with a spinner and no text, button `Scan sticker`; an empty scanned token fails the local checks; a 429 without `Retry-After` uses the full 10-minute cooldown.
  - 2026-11-17: first replay is a silent catch-up: with no stored last event id, replayed events advance the id and reach the screens but post no notification.
  - 2026-11-17: contract 0.8.0-draft also makes `event_id` required on both WS events and says `WS /ws` answers 401 on the upgrade for a bad token (on `feat/w4-contract`, Ionut reviews).
  - 2026-11-17: `SyncWorker` starts the headless task whenever a team code is stored, so the 15-minute event poll runs without pending segments.
  - 2026-11-17: Leaderboards labels approved as built: tabs `Individual`, `Team`, `Building`; season chips `Season {id}`; the building picker shows building names.
  - 2026-11-17: W4-6 runs on the 21 existing real traces in `traces/` (plus the synthetic set); no 20 new traces are recorded this week. This replaces the earlier "20 traces, 2 per condition per phone".
  - 2026-11-17: W4-7 is not done. The service survived on both phones, but the numbers can't be read because adb won't connect to the phones; the survival table in `docs/devices.md` stays as it is.
  - 2026-11-17: the pre-existing `App.test.tsx` failure (the session-restore test hit the real server through an unstubbed `fetch`) is fixed on `feat/w4-seam`, so every track inherits it.
  You make no entries of your own here.
- **Phone checks for Cristea:** only items you could not run here (W4-6 traces, W4-8 notification check and exit, the Samsung battery steps).
- **Surprises from the integration check:** field names, time zones, auth edges.

If the Android build or the Node tests cannot run on this machine, say so and list what you verified by reading the code.

## 5. Exit for Week 4

- Two phones on different teams: SM-S918B climbs, and SM-G985F's building standings flip live without a refresh.
- SM-G985F gets the notification for the lost building, and tapping it opens that building's standings; the same notification arrives through the poll with the app swiped away.
- The barometer-less path works on the emulator with `DEV_FORCE_NO_BAROMETER`, and once on a phone.
- Standings, leaderboards (three tabs, season selector), Home with today's verified figures and the pending count, history with rejection reasons, and onboarding all pass their tests and an emulator click-through.
- `docs/evaluation.md` holds the precision and recall of tuning pass 1 on the 20 new traces.
- Every row of "Plan coverage" is done, or listed as waiting with its reason.
- Blocked items are listed, each with its question for Cristea.
- The phone checks are listed for Cristea to run. They are not claimed.
