# Prompt: Cristea's Week 3 implementation (FloorWars)

**Status: prompt completed and checked against `IMPLEMENTATION_PLAN.md` on 2026-11-06, updated on 2026-11-08 for Ionut's Week 3 server (contract 0.5.1-draft). Implementation not started.**

You are implementing Cristea's part of Week 3 in `D:\FloorWars`. Work in one session, on feature branches from `main`. Follow the checklist in section 3 in order, except where a step says it can run in parallel. Tick each box only after its verification command has run and passed.

Week 3 is the critical path: a real stair climb in a building becomes points on the server. Goal from the plan: *walk up real stairs with the phone in a pocket; the segment lands in the DB as `verified`; team score and `building_claim` update; a duplicate upload is a no-op.*

## 0. Ground rules

- **Read only the docs in section 2.** Do not read the rest of `IMPLEMENTATION_PLAN.md`, Ionut's `/server` source code, or the Week 4 to 6 plan. The server is described by the contract and `server/README.md`; that is enough. If you need something outside the list, say which file and why before opening it.
- Codebase questions: `graphify-out/` exists, so run `graphify query "<question>" --budget 1500` (or `graphify path`, `graphify explain`) before reading files. Read files only for the lines you need.
- Contract first. Do not edit `contracts/openapi.yaml`. Contract changes are PRs reviewed by Ionut. If the contract blocks you, write the question under "Blocked" in section 4 and go on with other items.
- Do not edit `app/src/api/schema.ts` by hand. Regenerate it with `npm run generate:api` in `app/`.
- Do not install a new dependency without Cristea's approval. Dev tooling already named in this prompt (Prism through `npx`) is fine. Name the candidates, their licence and last release date, and wait for the answer. Cristea has approved Room and KSP (W3-2), Robolectric for tests only (W3-2) and WorkManager (W3-4). Anything else still needs an answer.
- Do not commit real sensor recordings. Read the header of each CSV before any commit (`docs/trace_format.md`).
- Do not log or store coordinates, and do not send anything beyond what `SegmentBatch` asks for (plan section 8, data minimisation).
- Branches, one PR each into `main`: `feat/w3-outbox` for W3-2 (native outbox, and the seam commit of W3-0), `feat/w3-engine` for W3-1, W3-3 and the gap metric of W3-7 (Kotlin, live segmenter and building attribution), `feat/w3-sync` for W3-4 and W3-5 (JS sync worker and status screen), `feat/w3-signout` for W3-6. The last three branch from `feat/w3-outbox` once the seam is committed. W3-8 is a check, not a branch. Do not run `git checkout` on `main` in a way that loses uncommitted work.
- **The staging server is up** (`https://api.floorwars.me/v1`), but Ionut's Week 3 work is not deployed. His code is merged on `main` (2026-11-07): migration `0004_segments`, `POST /v1/segments`, `GET /buildings`, building standings and leaderboards, contract 0.5.1-draft, and `server/app/api/v1/segments.py` is the route. The README lists it as "not yet deployed", so the deployed server still answers 404 on `POST /v1/segments` (W3-0 re-checks it). `/config` is Week 5 work. Build and test against the Prism mock (`npm run mock:api` at the repo root, port 4010) until the Wednesday check; the switch to the real server is W3-9.
- Before you claim any item done, run its verification command and paste the summary line into your report. No claim without output.
- If a root cause is unclear for a failing test, find the cause first, then fix. Do not patch around a symptom.

## 1. Current state (checked 2026-11-06)

- **Week 2 is complete and validated** on Cristea's side and Ionut's side. PRs #38 to #41 are merged. The Week 2 summary is `cristea/week_2/week_2_summary.md` (do not read it in full; the facts you need are below).
- **Segmenter and classifier exist and are pure Kotlin**: `segmenter/Segmenter.kt` (`Segmenter.segment(pressure, steps): List<Segment>`, 8 s centred median, climbing at >= 0.05 m/s over 4 s, runs under 15 s apart joined, under 1 m dropped) and `classifier/Classifier.kt` (STAIRS / ELEVATOR / OTHER plus a reason, thresholds in `ClassifierThresholds`, elevator threshold is 0.5 m/s). `classifier/StepScoring.kt` holds the steps-per-metre rule. They run on a whole recording, not on a live stream. **W3-1 has to make them work on a growing buffer.** Do not duplicate their rules.
- **Live sensing today only logs traces.** `FloorSensorsService.kt` is a foreground service (type `health`) that registers `TYPE_PRESSURE` and `TYPE_STEP_DETECTOR` and fills a `SensorEventBuffer` (`RawSensorEvent(sensorType, timestampNanos, values)`). `FloorSensorsModule.kt` exposes `startLogging`, `stopLogging`, `getStatus`, `saveTrace`. Nothing runs the segmenter on live data, there is no outbox, and there is no sync.
- Real rates: pressure about 25 Hz (SM-S918B) or 10 Hz (SM-G985F) at `SENSOR_DELAY_GAME`; step events lag pressure by up to 240 ms measured (the code tolerates 300 ms) and arrive out of order. Windows are in seconds, never samples.
- **No persistence or background-work library is installed.** There is no Room, no WorkManager, no background-fetch in `app/package.json` or the Gradle files (checked). W3-2 adds Room and W3-4 adds WorkManager, both approved.
- **Auth and check-in are done** (Week 2): `app/src/auth/session.ts` (`endSession()` already exists, it clears tokens and the team flag), `app/src/api/client.ts` (single-flight 401 refresh, accepts `application/problem+json`), `app/src/checkin/` (`state.ts`, `qr.ts`, `deps.ts`, `deviceLibs.tsx`). A successful `POST /checkins` returns `id`, `building_id`, `valid_from`, `valid_until`. **The app does not keep the active check-in anywhere yet.** W3-3 needs it in a place the native service can read.
- **`GET /config`** is in the contract and returns `version` (for example `rules-1`) and the thresholds. The native thresholds are compiled in, so a segment carries the version the app was built with: a named constant next to `ClassifierThresholds`, not a value fetched at runtime.
- Home and status are placeholders in `app/src/screens/PlaceholderScreens.tsx`. `app/src/ui/parts.tsx` holds the shared look (warm paper background, one orange accent, system fonts). There is no sign-out button yet.
- CI: `.github/workflows/app.yml` (android job with ktlint, unit tests and the trace-replay precision gate; node job with lint, typecheck, Jest, and the generated-client check) and `.github/workflows/server.yml`. There is no separate replay workflow. `app.yml` must stay green.
- Test devices: SM-S918B and SM-G985F. Real traces: 21 in `traces/`, synthetic: 24 in `fixtures/synthetic/`. Do not move files.
- **Carried over from Week 2**: the phone tests of the entrance-QR check-in (scan a printed code, camera permission off, airplane mode). They need Ionut's printed codes for both buildings. They are Cristea's checks (W3-8).

## 2. Documents to read (and only these)

| Doc | Which part | Needed for |
|---|---|---|
| `IMPLEMENTATION_PLAN.md` | Section 10, "Week 3" (Cristea and exit lines only) | All |
| `IMPLEMENTATION_PLAN.md` | Section 3.1 (climb-to-claim sequence), 3.3 (sensor fusion, thresholds) and 3.4 (anti-cheat layers, layer 1) | W3-1, W3-3 |
| `IMPLEMENTATION_PLAN.md` | Section 7.10 (mobile network-failure strategy) | W3-4 |
| `IMPLEMENTATION_PLAN.md` | Section 2 (segment bounds, check-in rules) | W3-1, W3-3 |
| `IMPLEMENTATION_PLAN.md` | Section 4.1, 4.2 and 4.3 (stack, RN libraries, native module) | W3-2, W3-4 |
| `IMPLEMENTATION_PLAN.md` | Section 8 (data minimisation, input validation) | W3-2, W3-4 |
| `IMPLEMENTATION_PLAN.md` | Section 9.2 (working rules) and 9.3 (Week 3 Wednesday row) | W3-9 |
| `server/README.md` | Sections "Segments" (if present), "Check-in" and "Auth" | W3-3, W3-4 |
| `tools/e2e/README.md`, `tools/e2e/e2e_check.py` | Whole files. The reference for the order of calls | W3-4, W3-9 |
| `contracts/prism/README.md` | Whole file | W3-4 |
| `docs/trace_format.md` | Sections 1, 3, 4 and 7 | W3-1, W3-7 |
| `.github/workflows/app.yml` | Whole file | All (CI must stay green) |
| `contracts/openapi.yaml` | Paths `/segments`, `/config`, `/me/segments`, `/checkins`, and the schemas they reference (`SegmentBatch`, `SegmentBatchResult`, `Segment`, `SegmentFields`, `AcceptedSegment`, `RejectedSegment`, `BuildingFlip`, `ClassifierConfig`, `Checkin`, `Problem`) | W3-2, W3-3, W3-4 |
| Code | `Segmenter.kt`, `Classifier.kt`, `StepScoring.kt`, `TraceCsv.kt`, `SensorEventBuffer.kt`, `FloorSensorsService.kt`, `FloorSensorsModule.kt`, `app/src/native/NativeFloorSensors.ts`, `app/src/native/floorSensors.ts`, `app/src/auth/session.ts`, `app/src/api/client.ts`, `app/src/checkin/state.ts`, `app/src/screens/PlaceholderScreens.tsx`, `app/src/navigation/RootNavigator.tsx` | Matching files |

Do not read `cristea/week_1/*` or `cristea/week_2/*` in full. Read `cristea/week_2/finish_week_2.md` only for W3-8 (the three QR phone test rows and the "If something goes wrong" table).

## 3. Checklist

Dependencies: W3-0 first. Then two tracks in parallel: **Track A** (native: W3-1 → W3-3, and W3-2 alongside) and **Track B** (JS: W3-4 → W3-5, and W3-6 alongside). W3-7 and W3-8 need a phone. W3-9 last.

The module API between native and JS is the seam. This session commits it in W3-0, so all four agents build against it from their first commit. `NativeFloorSensorsSpec` is generated from `NativeFloorSensors.ts`, and `FloorSensorsModule` extends it, so every new method needs a Kotlin override or the Android build fails. The seam commit therefore has both sides: the types below, and Kotlin overrides that reject "not implemented" (void methods do nothing) until their owner fills them in.

```ts
// NativeFloorSensors.ts additions

// Exactly the fields of the contract's Segment, which allows no others.
export type PendingSegment = {
  id: string;
  checkin_id: string;
  started_at: string; // ISO 8601 UTC
  building_id: number;
  ascent_m: number;
  duration_s: number;
  vert_speed_mps: number;
  steps: number;
  stair_prob: number;
  classifier_version: string;
};
export type ActiveCheckin = { checkin_id: string; building_id: number; building_name: string | null; valid_until_ms: number };
export type PendingChanged = { pending: number };

// FloorSensorsStatus gains (w3-engine fills them; the seam returns false, null and 0):
//   detecting: boolean; last_segment_ms: number | null; rejected_count: number;
//   no_checkin_count: number; longest_gap_s: number; gaps_over_threshold: number;

// Spec gains
setActiveCheckin(checkinId: string, buildingId: number, buildingName: string | null, validUntilMs: number): void; // w3-engine
clearActiveCheckin(): void;                                                           // w3-engine
getActiveCheckin(): Promise<ActiveCheckin | null>;                                    // w3-engine
readonly onPendingChanged: CodegenTypes.EventEmitter<PendingChanged>;                 // w3-engine
getPending(limit: number): Promise<PendingSegment[]>; // oldest first, status = pending; w3-outbox
markSynced(ids: string[]): Promise<void>;                                             // w3-outbox
markRejected(ids: string[], reason: string): Promise<void>;                           // w3-outbox
getPendingCount(): Promise<number>;                                                   // w3-outbox
clearPending(): Promise<void>;                                                        // w3-outbox
isIgnoringBatteryOptimizations(): Promise<boolean>;                                   // w3-sync
openBatteryOptimizationSettings(): void;                                              // w3-sync
```

W3-1 and W3-2 also run in parallel, so the seam has a Kotlin side, in `outbox/SegmentOutbox.kt` with no Android imports. `w3-engine` writes through this interface with a fake in its tests. `w3-outbox` implements it.

```kotlin
data class OutboxSegment(
    val id: String,
    val checkinId: String,
    val buildingId: Int,
    val startMs: Long,
    val endMs: Long,
    val ascentM: Double,
    val durationS: Double,
    val vertSpeedMps: Double,
    val steps: Int,
    val stepsPerM: Double,
    val pressureStepsMatch: Boolean,
    val stairProb: Double,
    val classifierVersion: String,
    val hasBarometer: Boolean,
)

interface SegmentOutbox {
    fun insert(segment: OutboxSegment)
}
```

Keep it a single seam. A change to it goes in the report under "Decisions".

### 3.1 Subagents and worktrees

The work is delegated to project subagents in `.claude/agents/`. Each one owns the checklist items below. This session coordinates: it starts the agents with the Agent tool, routes their blockers, runs the checks, commits the seam, and does W3-9. It does not implement the delegated items itself.

| Agent | Items | Worktree | Model, effort |
|---|---|---|---|
| `w3-preflight` | W3-0 (all but the seam) | main checkout (creates the outbox worktree) | haiku, low |
| `w3-outbox` | W3-2 | `D:/FloorWars-w3/outbox` | opus, high |
| `w3-engine` | W3-1, W3-3, W3-7 (gap metric) | `D:/FloorWars-w3/engine` | opus, high |
| `w3-sync` | W3-4, W3-5 | `D:/FloorWars-w3/sync` | sonnet, medium |
| `w3-signout` | W3-6 | `D:/FloorWars-w3/signout` | sonnet, low |

Order:

1. Start `w3-preflight` first. Wait for its report.
2. This session commits the seam on `feat/w3-outbox`, runs both verify commands on it, then creates the other three worktrees from that branch.
3. Track A and Track B run in parallel, each agent in its own worktree: `w3-outbox`, `w3-engine`, `w3-sync` and `w3-signout`. `w3-engine` does W3-1, then W3-3, then the gap metric of W3-7.
4. W3-9 and the phone checks of W3-7 are done in this session, after all agents report.

Rules for this session:

- Start each agent with the Agent tool. Give it the item IDs and its worktree path in the prompt. Its own `.claude/agents/<name>.md` holds its scope, documents and rules.
- Re-run each item's verify command yourself before you tick its box. Agent reports are evidence, not proof.
- If an agent lists a Blocked item, copy it to section 4 and carry on with the other items.
- Worktrees need the project skills and agents copied in, because `.claude/` is gitignored. They also need `npm ci` in `app/`, because `node_modules` is not shared and the Android build reads it too.
- UI items (W3-5, W3-6) must use the impeccable skills (`impeccable:*`, from the plugin enabled in `.claude/settings.json`). Their agent files require it, and a UI agent that cannot load them stops the screen work and reports.
- `w3-outbox` and `w3-engine` both edit `FloorSensorsModule.kt` and `FloorSensorsService.kt`. The outbox merges first, and the engine rebases on it, which is the PR order in W3-9.
- If the Agent tool does not list these agents, restart the session. Project agents load when a session starts. The Week 2 agents were removed.
- Section 2 applies to the agents too. They read only the documents their agent file names.

Commands (also the reference for the paths):

```
# w3-preflight:
git worktree add D:/FloorWars-w3/outbox -b feat/w3-outbox main
# this session, after the seam commit on feat/w3-outbox:
git worktree add D:/FloorWars-w3/engine  -b feat/w3-engine  feat/w3-outbox
git worktree add D:/FloorWars-w3/sync    -b feat/w3-sync    feat/w3-outbox
git worktree add D:/FloorWars-w3/signout -b feat/w3-signout feat/w3-outbox
# for each worktree:
mkdir -p <worktree>/.claude && cp -r D:/FloorWars/.claude/skills D:/FloorWars/.claude/agents D:/FloorWars/.claude/settings.json <worktree>/.claude/
cd <worktree>/app && npm ci
```

Do not run `git checkout` in `D:\FloorWars`. Check `git worktree list` after each addition.

### W3-0 Preflight (first)

*Delegate: `w3-preflight`, except the seam, which this session commits.*

- [ ] `git status` and `git branch --show-current`. Confirm `main` is up to date with `origin/main`. The working tree should be clean apart from this prompt; list anything else, do not touch it.
- [ ] Baseline, before any change, and record the summary lines: `cd app/android && ./gradlew test ktlintCheck` and `cd app && npm run lint && npm run typecheck && npm test`.
- [ ] `curl.exe -i https://api.floorwars.me/healthz`, and check whether `POST /segments` exists on the server (`GET /openapi.json` or the README status table). Record the answer: it decides whether W3-9 can run this week.
- [ ] Create the `feat/w3-outbox` worktree, copy `.claude` into it and run `npm ci` (commands in section 3.1).
- [ ] This session: commit the seam of section 3 on `feat/w3-outbox` (TypeScript types, Kotlin overrides that reject, `outbox/SegmentOutbox.kt`). Run both verify commands on it. Then create the other three worktrees from it.
- Done when: both baselines are recorded, the server state is known, and all four worktrees hold the seam. Pre-existing failures are listed, not fixed silently.

### W3-1 Live segmenter in the service (Track A, Kotlin)

*Delegate: `w3-engine` (worktree `D:/FloorWars-w3/engine`).*

- [ ] A pure-Kotlin `LiveSegmenter` (no Android imports) that takes events as they arrive and emits finished segments: it keeps a bounded rolling window (long enough for the 8 s median plus the longest open climb, for example 4 minutes), calls the existing `Segmenter` and `Classifier` on it, and emits each segment exactly once, only after it has closed (climb ended plus the join gap of 15 s, so a landing is not split). No second copy of the rules.
- [ ] Segments that cross the window edge, or an open climb when the service stops, are flushed on stop and counted in a local counter. A segment is never emitted twice and never lost across two consecutive calls.
- [ ] Only STAIRS segments with a pressure-steps match go to the outbox (plan 3.4 layer 1, on-device reject), and only inside the contract's bounds (`ascent_m` 2.0 to 120, `steps` 1 to 2000), because the segmenter keeps climbs from 1 m and the server would reject the smaller ones. Count the rejected ones in `rejected_count`; do not store them. Write through `SegmentOutbox`.
- [ ] Wire it into `FloorSensorsService.kt`: a mode that detects without recording a trace (recording stays for the logger screen). Sampling rate: choose `SENSOR_DELAY_GAME` (10 to 25 Hz) as the default, state it in a constant, and keep the batching of the sensor delivery (`maxReportLatencyUs`) as a named constant to save battery. The sensors and the wake lock run only while the user has an active check-in: stop both when the check-in expires.
- [ ] Wake-lock strategy (Cristea's decision, 2026-11-06): hold a `PARTIAL_WAKE_LOCK` only during an active check-in, with a timeout at the check-in's expiry, because non-wakeup sensors stop delivering when the CPU sleeps (`FloorSensorsService.kt` already does this for logging). State the reason in a code comment. W3-7 records the battery cost.
- [ ] Time base: use `SystemClock.elapsedRealtimeNanos` timestamps from the events. Convert to wall-clock only when a segment is stored, with one stated offset, so a clock change does not corrupt durations.
- [ ] JUnit tests: feed the real traces in `traces/` and the synthetic ones through `LiveSegmenter` in small chunks (1 s, 5 s, one event at a time) and assert the emitted segments equal what the batch `Segmenter` gives on the whole file. Add: out-of-order step events across a chunk edge, a climb that starts in one call and ends in the next, a stop in the middle of a climb, no duplicate emissions.
- Verify: `cd app/android && ./gradlew test ktlintCheck`. Paste the summary line. The existing trace-replay gate must still pass unchanged.
- Done when: chunked replay equals batch replay on all 45 traces, and the tests fail if the "emit once" rule is broken (break it once, check, revert).

### W3-2 Native outbox (Track A, Kotlin)

*Delegate: `w3-outbox` (worktree `D:/FloorWars-w3/outbox`). The seam commit is already on this branch.*

- [ ] Room, as the plan says (approved by Cristea, 2026-11-06). Add Room and the annotation processor it needs (KSP, at the version that matches the project's Kotlin), and no other runtime dependency. Report the version, licence and release date.
- [ ] Table `segment_outbox`: client UUID (`id`, generated at creation, never reused), `start_ms` and `end_ms` (wall clock), the features of the contract's `Segment` (`ascent_m`, `duration_s`, `vert_speed_mps`, `steps`, `stair_prob`, `classifier_version`), and the local-only columns `steps_per_m`, `pressure_steps_match` and `has_barometer`, plus `checkin_id`, `building_id`, `status` (`pending`, `synced`, `rejected`), `reject_reason`, `created_at`, `attempts`. Take field names from the contract schema, not from memory.
- [ ] Module API from section 3: `getPending(limit)` oldest first, `markSynced(ids)`, `markRejected(ids, reason)`, `getPendingCount()`, `clearPending()`. All idempotent: marking an already-synced id is a no-op. `getPending` returns the ten `PendingSegment` fields and nothing else, with `started_at` as ISO 8601 UTC. Implement `SegmentOutbox.insert` from the seam.
- [ ] Retention: delete `synced` rows older than 7 days and `rejected` older than 30 days on service start. Pending rows are never deleted by age. Cap the table at 5000 rows, as a named constant: drop the oldest `rejected`, then the oldest `synced`. Never drop pending rows: when the table is full of pending rows, refuse the new segment and count it in a debug counter.
- [ ] The write must survive the process being killed: insert in a transaction, no in-memory-only queue. Test with a kill between insert and the next call.
- [ ] Tests: insert, `getPending` order and limit, `markSynced` twice, retention, cap, and a row written before a simulated restart is still pending after. Use Robolectric (test-only, approved) only if the plain JUnit setup cannot reach the database; say which and why.
- Verify: `cd app/android && ./gradlew test ktlintCheck`. Paste the summary line.
- Done when: the API works against the tests, and `PendingSegment` matches the contract's `Segment` one to one.

### W3-3 Attribute segments to the active check-in (Track A, Kotlin and JS)

*Delegate: `w3-engine` (same worktree, after W3-1). JS part in `app/src/checkin/`.*

- [ ] After a successful `POST /checkins`, the app calls `setActiveCheckin(id, building_id, building_name, valid_until_ms)`, with the name from `GET /buildings`, or null when that call fails. A new check-in replaces it; W3-6 clears it on sign-out. The value survives an app restart (the service can outlive the JS runtime), so store it natively, not in JS memory, and expose it through `getActiveCheckin()`.
- [ ] The service stamps each emitted segment with the check-in that was active at the **start** of the climb. A climb that starts inside the validity window and ends after `valid_until` still counts for that check-in. A climb with no active check-in is **not stored** (no building to attribute to) and counted in `no_checkin_count`; say so in the report. The rules classifier gives no probability and the contract requires `stair_prob`: use a named constant of 1.0 (only STAIRS segments are stored), and list it under "Decisions".
- [ ] A new check-in ends the previous one on the server (Week 2 behaviour); the app mirrors that: later segments belong to the new one, earlier ones keep theirs, even when they upload after the swap.
- [ ] The barometer and step sensors run only while a check-in is active (W3-1); starting and stopping follow `setActiveCheckin` and expiry, and the persistent notification text says which building (the name when known) and how long.
- [ ] Jest test: success of `POST /checkins` calls `setActiveCheckin` with the right values. JUnit test: attribution at the window edges (start inside, end outside; start outside), and a check-in swap in the middle of a recording.
- Verify: `cd app/android && ./gradlew test ktlintCheck` and `cd app && npm run lint && npm run typecheck && npm test`. Paste the summary lines.
- Done when: every segment in the outbox has a `checkin_id` and `building_id`, and none can exist without them.

### W3-4 JS sync worker (Track B, TypeScript)

*Delegate: `w3-sync` (worktree `D:/FloorWars-w3/sync`). It builds against a fake native module in Jest, so it does not wait for W3-2.*

- [ ] Run `npm run generate:api` first; if `schema.ts` differs from the one on `main`, commit it with the code that needs it.
- [ ] `app/src/sync/` with a worker that: reads `getPending(limit)` (batch size a named constant, at most the contract's limit of 100), builds a `SegmentBatch` as `{ device_id, segments }` (contract 0.5.0-draft: `device_id` is required, at batch level), and sends `POST /segments` through the generated client with an `Idempotency-Key`. The key is stored with the batch (derived from the sorted segment ids, or saved in the outbox) so a retry of the same batch reuses the same key, and a new batch gets a new one.
  - `device_id` is the id the app registered at sign-in: `getDeviceId()` from `app/src/auth/session.ts` (stored in the Keychain, the same value `getDeviceInfo()` sends). Never a new UUID. It is not a field of `PendingSegment` and is not stored in the outbox.
  - `segments` holds the ten `PendingSegment` fields only, because the contract's `Segment` refuses any other field.
- [ ] Per-segment handling of `SegmentBatchResult`: accepted ids go to `markSynced`; each rejected id goes to `markRejected` with the server's rule name; flips in the response are passed to a callback for Week 4 (do not build UI for them). A repeat of an already-stored segment comes back accepted **without `points`** (`points` is optional), and the worker treats it as done. Store whatever reason string the server sends: the enum grew in 0.5.0 (`started_at_range`, `season_inactive`, `no_team`, `stair_prob_range`) and Ionut has decided on an `overlap` reason that is not in the contract yet, so do not switch on the enum or drop an unknown reason.
- [ ] Failure handling per plan 7.10:
  - Network error, 5xx and **503** (Valkey or another dependency down): back off with exponential delay and full jitter (base, cap and max attempts as named constants), the batch stays pending. A 503 with `Retry-After` honours it.
  - 429 honours `Retry-After`.
  - 401 goes through the existing refresh and, if that signs out, the worker stops.
  - 422 for a whole batch is a bug: mark nothing, log the problem type once, stop retrying that batch, and report it for the status screen (W3-5). The rows stay pending and later segments wait, because nothing is lost and a 422 needs an app fix.
  - **403 `device-unknown`** (the `device_id` is not a device of the signed-in user): same as 422. Mark nothing, log the problem type once, stop retrying, keep the rows pending, report it for the status screen. Do not sign out and do not generate a new device id.
- [ ] Single flight: one sync at a time, whatever triggers it. A second trigger while one is running is ignored or queued once.
- [ ] Timeouts per plan 7.10, in `app/src/api/client.ts`: 10 s until the response headers arrive (`fetch` has no separate connect timeout, so this stands in for connect) and 20 s to read the body, both through `AbortController`, with no new library. A timeout counts as a network error.
- [ ] Triggers: on app foreground, after a new segment (debounced, from `onPendingChanged`), and a periodic background run. The background run (Cristea's decision, 2026-11-06): a Kotlin WorkManager job, every 15 minutes with a connected-network constraint, wakes the JS worker through React Native's Headless JS. Add WorkManager (approved) and no other library. The job never uploads by itself.
- [ ] Tests (Jest, fake native module and fake client): batching, the batch carries `device_id` from `getDeviceId()` and the segments carry only the ten fields, idempotency key reuse on retry and fresh key on a new batch, accepted / rejected / duplicate handling (a duplicate without `points`, an unknown reason string), backoff with a fixed random source, `Retry-After` on 429 and 503, 401 stop, 403 and 422 stop with rows still pending, single flight, timeouts, and a batch that partly fails.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`, and `npm run generate:api` followed by `git diff --exit-code app/src/api/schema.ts`, and `cd app/android && ./gradlew test ktlintCheck`. Paste the summary lines.
- Done when: the worker drains a fake outbox against the Prism mock (`npm run mock:api`; say whether you used `--dynamic`), and the Jest tests pass.

### W3-5 Status screen (Track B, React Native)

*Delegate: `w3-sync` (same worktree, after W3-4). Load the impeccable skills first.*

- [ ] Replace the Home / status placeholder. Shows: whether the service is running (`detecting`), the active check-in (`getActiveCheckin()`, the building name when known, no name until `GET /buildings` is deployed, minutes left, same rounding rule as the check-in screen), time of the last segment (`last_segment_ms`), pending count (`getPendingCount()`), last sync result, and the battery-optimisation hint. Until W3-1 and W3-2 are merged, these come from the seam stubs and the Jest fake.
- [ ] Battery-optimisation hint: only on Android, only when the app is not exempt. Implement the Kotlin side of `isIgnoringBatteryOptimizations()` (`PowerManager.isIgnoringBatteryOptimizations`) and `openBatteryOptimizationSettings()`. One short sentence that says what is lost, and a button that opens the system setting. No hint on exempt devices.
- [ ] A "Sync now" button that triggers the worker (single flight applies).
- [ ] States: loading, no active check-in (say what to do: check in at the building), service not running, offline, error (including a batch stuck on 422 or 403 `device-unknown`). No numbers are invented: if a value is unknown, say so.
- [ ] Keep the check-in button from Week 2 reachable from here.
- [ ] Jest tests for each state and for the hint's visibility rule.
- Verify: `cd app && npm run lint && npm run typecheck && npm test` and `cd app/android && ./gradlew test ktlintCheck`. Paste the summary lines.
- Done when: every state renders and is tested, and the screen was clicked through on the emulator against the Prism mock (record it element by element in the PR description).

### W3-6 Sign out button (Track B, React Native)

*Delegate: `w3-signout` (worktree `D:/FloorWars-w3/signout`). Load the impeccable skills first.*

- [ ] A **Sign out** button on Home (it does not need to wait for W3-5; keep the change small so it merges into either shape of Home).
- [ ] It calls `endSession()` from `app/src/auth/session.ts`, which clears the tokens and the team flag and returns to sign-in. Ask for a confirmation first, and say how many segments are not uploaded yet and that they will be deleted (`getPendingCount()`). A different user signing in must not inherit them, and the contract gives the app no user id to tag rows with (`/me` has only `DELETE`), so `clearPending()` is the choice. Put it under "Decisions" with this reason.
- [ ] `endSession()` itself calls `clearPending()` and `clearActiveCheckin()`, which also stops the sensors, so the sign-out forced by a failed refresh does the same. A native failure must not stop the sign-out.
- [ ] A server-side revoke endpoint does not exist yet, so the old refresh token stays valid until it expires. Do not fake a revoke; list it under "Blocked" as a request to Ionut.
- [ ] Jest tests: confirm shows, cancel does nothing, confirm calls `endSession` and navigates to sign-in, and `endSession` calls `clearPending` and `clearActiveCheckin`, including when one of them fails.
- Verify: `cd app && npm run lint && npm run typecheck && npm test`. Paste the summary lines.
- Done when: after sign out the app opens on the e-mail screen, and a second sign-in on the same phone works without clearing app data.

### W3-7 Service survival and the gaps metric (needs a phone)

*Gap metric: delegate `w3-engine`, after W3-3. Phone checks: done in this session with Cristea. Not claimed until Cristea runs them on both phones.*

- [ ] "Sessions with gaps": the service logs, per check-in session, the longest gap between pressure events (in seconds) and the number of gaps over a named threshold (for example 5 s). Read through `getStatus()` (`longest_gap_s`, `gaps_over_threshold`); never uploaded. Add a JUnit test for the gap counter. Verify: `cd app/android && ./gradlew test ktlintCheck`.
- [ ] Phone checks for Cristea, on both SM-S918B and SM-G985F, with a check-in active and the app in the state below. For each: ten minutes with the phone in a pocket, then one stair climb, then read the gap metric, the pending count and the battery percentage (note it before the run too).
  - Screen off.
  - App swiped away from recents.
  - Battery saver on.
  - Battery optimisation not exempt (the default), screen off for 20 minutes.
- [ ] Write the results in a table in `docs/devices.md` (device, state, longest gap, gaps over threshold, segment found yes/no, battery used). If the service dies in any state, record the state and what Android did (logcat line), and add the fix to the Blocked list rather than guessing.
- Done when: the table exists with all eight rows filled by Cristea, or the missing rows are listed as pending.

### W3-8 Carried over from Week 2: QR check-in phone tests (needs Ionut's printed codes)

*Cristea's checks. Do not mark them done.*

Rows from `cristea/week_2/finish_week_2.md`, step 7:

- [ ] Row 5: **Check in**, **Scan entrance code**, allow the camera, point at the printed code. Expected: "Checked in: Facultatea de ..., 90 min left" and **Done** (the app rounds minutes up, so 90 right after checking in). Until `GET /buildings` is deployed the app shows no building name: record that as pending, not as a failure.
- [ ] Row 8: Phone settings, Apps, FloorWars, Permissions: set Camera to **Don't allow**, then **Scan entrance code**, and tap **Don't allow** if Android asks again. Expected: "Camera access is off. Allow it in Settings, or check in with your location." and **Open Settings** opens the app's settings.
- [ ] Row 10 with the camera allowed again: airplane mode on, scan the printed code. Expected: "Could not check in. Check your connection, wait a moment, and try again."
- [ ] Also scan an expired and a foreign code if Ionut has one, and record the messages.
- [ ] Ask Ionut for the printed codes for both buildings now (valid on the test day, `--days` at most 31). Add that request to "Blocked" in your report.
- Done when: Cristea has run the rows and recorded the results in the PR description of W3-5 or in a short note in `cristea/week_3/`.

### W3-9 Integration, the Wednesday check and exit (last)

*Done in this session, not delegated. Runs after all tracks report.*

- [ ] Merge all four branches into a local throwaway branch and run `cd app/android && ./gradlew test ktlintCheck` and `cd app && npm run lint && npm run typecheck && npm test` on it, so the tracks are proven together before any PR.
- [ ] Open one PR per branch into `main`, in this order: `feat/w3-outbox`, `feat/w3-engine`, `feat/w3-sync`, `feat/w3-signout`. Rebase each on `main` after the previous one merges. Ask Ionut for review on the parts that touch the contract (`/segments`, `/checkins`). Each PR says "tested against the Prism mock only" until the Wednesday check passes. CI must be green (`android unit tests and trace replay`, `lint, typecheck, test, API client`).
- [ ] **Wednesday check** (as early in the week as the code allows, ugly is fine): when W3-1, W3-2, W3-3 and W3-4 are on a build, and Ionut says `POST /segments` is deployed, check `https://api.floorwars.me/healthz`, build the release APK (`cristea/week_2/finish_week_2.md`, step 5), install it, check in, walk up real stairs with the phone in a pocket, and watch the segment arrive as `verified` and the building owner change. Run `tools/e2e/e2e_check.py` once to confirm the server still matches the contract (its `--upload` mode, with `--qr-token-file`, also uploads fake segments and reads the standings). Check that Ionut's server accepts 4 to 10 steps per metre: on 2026-11-07 it rejected above 8 (`STEPS_PER_M_MAX` in `server/app/segments/rules.py`), and pocket climbs measured 6.7 to 8.7, so a pocket climb rejected as `pressure_steps_mismatch` means the fix is not deployed, not that the app is wrong. Record everything that surprised you (field names, time zones, auth edges, rounding) in the report.
- [ ] Exit, on a real phone (not claimed until Cristea runs it): the segment lands in the DB as `verified`; the team score and `building_claim` update; re-sending the same batch is a no-op (kill the app after upload but before `markSynced`, reopen, and confirm the duplicate is accepted and no points are added twice).
- [ ] Update the README status row for "App, week 3" add the decisions of this week to "Decisions taken", dated, and update `IMPLEMENTATION_PLAN.md` for anything that changed from it this week (docs rule, section 9.3).
- Done when: each PR's CI is green, and the report lists the phone checks (W3-7, W3-8, the exit climb) as Cristea's and the Wednesday check as done or pending on Ionut's deploy.

## 4. Report format

After each checklist item, post one line: `W3-n done | verify: <command> → <summary line> | commit: <sha>`. Agents post the same line in their reports. Copy them here after you have re-run the verify command. Keep these sections up to date in your final report:

- **Blocked:** items waiting on Cristea or Ionut, one line each, with the default you would use. Expect at least: `POST /segments` deployed (W3-9), `GET /buildings` deployed (W3-5, W3-8 row 5, the notification), the server's steps-per-metre upper bound raised from 8 to 10 to match plan 3.3 and `StepScoring.kt` (W3-9, the exit climb), `overlap` added to the contract's rejection reasons (W3-4), printed QR codes (W3-8), revoke endpoint (W3-6), a gap-metric endpoint before the pilot (W3-7).
- **Decisions:** choices you made (window length, sampling rate, retention, batch size), one line each, with the reason. Cristea already decided, so record these as his (2026-11-06): Room for the outbox, `stair_prob` a constant 1.0, `clearPending` on sign-out, the wake lock during a check-in, the check-in driving the sensors, attribution by climb start, WorkManager with Headless JS, 429 honouring `Retry-After`, a 422 batch staying pending, a 403 `device-unknown` batch handled like a 422 (2026-11-08), `device_id` from `getDeviceId()` (2026-11-08), 10 s and 20 s timeouts, the 5000-row cap, the gap metric staying local, the status screen extras, Robolectric for tests only, Ionut's review on the contract parts only.
- **Phone checks for Cristea:** only items you could not run here (W3-7, W3-8, the exit climb).
- **Surprises from the Wednesday check:** field names, time zones, auth edges.

If the Android build or the Node tests cannot run on this machine, say so and list what you verified by reading the code.

## 5. Exit for Week 3

- The live service runs the segmenter and classifier on real sensor events; chunked replay equals batch replay on all traces; the trace-replay gate still passes.
- Segments are stored in a durable outbox with client UUID, status, check-in id and `has_barometer`, and attributed to the building of the active check-in.
- The sync worker uploads batches with `Idempotency-Key`, backs off with jitter, and handles accepted, rejected and duplicate segments per item.
- The status screen and the sign-out button exist and are tested.
- The Wednesday check is done, or pending on Ionut's deploy with the reason written down.
- Blocked items are listed with a default each.
- The phone checks (service survival on both phones, the QR rows carried over from Week 2, the exit climb) are listed for Cristea to run. They are not claimed.
