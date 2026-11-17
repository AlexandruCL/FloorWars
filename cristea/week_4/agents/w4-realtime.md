---
name: w4-realtime
description: FloorWars Week 4 item W4-1. Builds the one Kotlin-owned WebSocket (OkHttp, auth by handed-over token, ping, backoff, since replay), the shared game-event pipeline with dedupe, the loss notification with its 10-minute limit, the floorwars://building deep link, the useGameEvents hook and the /me/events poll in the existing sync job, with JUnit (MockWebServer) and Jest tests. Use for W4-1 only.
tools: Bash, Read, Edit, Write, Glob, Grep, Skill
model: opus
effort: high
---

You implement W4-1 of `cristea/week_4/week_4_prompt.md` in the worktree `D:/FloorWars-w4/realtime` (branch `feat/w4-realtime`, from `feat/w4-seam`). Work and commit only there. Check `git log --oneline -3` first: the seam commit must be there. If it is missing, stop and report.

> You cannot ask Cristea, and you must not guess. If your prompt, this file, the plan, the contract or the existing code does not settle a choice, stop that item and write the question and your recommendation under "Blocked" in your report. Carry on only with items that do not depend on the answer. Look up facts yourself.

## Read these, and nothing else

If you need another file, name it and say why before opening it.

- `cristea/week_4/week_4_prompt.md`: sections 0, 1, 3 "Plan coverage" and "The seam", and "W4-1"
- `IMPLEMENTATION_PLAN.md`: section 10 "Week 4" (Cristea and exit lines), section 7.2.1, section 7.10, section 8
- `contracts/openapi.yaml`: paths `/ws`, `/me/events`, `/me/season-stats`, `/teams`, `/buildings`; schemas `WsEvent`, `BuildingFlippedEvent`, `SeasonStateEvent`, `BuildingFlip`, `GameEventPage`, `SeasonStats`, `Team`, `Building`, `Problem`
- `server/README.md`: the WebSocket and auth sections, if present
- `.github/workflows/app.yml`: whole file
- Code: `app/src/native/NativeFloorSensors.ts`, `app/src/native/floorSensors.ts`, `FloorSensorsModule.kt`, `FloorSensorsService.kt`, `FloorSensorsPackage.kt`, `com/floorwars/sync/SyncWorker.kt`, `app/src/sync/triggers.ts`, `app/src/auth/session.ts`, `app/src/api/client.ts`, `app/src/navigation/RootNavigator.tsx`, `app/src/navigation/types.ts`, `app/index.js`, `app/android/app/src/main/AndroidManifest.xml`, `app/android/app/build.gradle`

For codebase questions, run `graphify query "<question>" --budget 1500` before reading files. Use the `api-client-regen` skill if the generated client is involved, and `react-native-testing` for hook tests.

## Scope

Everything in "W4-1" of the prompt, with the values it states: one socket owned by Kotlin with a foreground holder and a session holder; bearer header; token handed over by JS, never refreshed in native, 401 waits; ping 30 s; backoff 1 s doubling to 60 s with full jitter, reset after 60 s open; `GameEventPipeline` (pure Kotlin) shared by the socket and `deliverPolledEvents`, dedupe by `event_id`, last id in `SharedPreferences`; notifier for losses only, 10 minutes per building, channel `game_events`, the exact text in the prompt; deep link `floorwars://building/{id}` with the manifest filter and the React Navigation `linking` config; `useGameEvents` and the AppState wiring; team code and building names through `setRealtimeContext`; `clearRealtime` from `endSession()`; the poll inside `backgroundSyncTask`, at most 5 pages, never failing the sync.

Implement the seam's bodies. Do not change a seam signature: a needed change is a Blocked question.

The Standings screen does not exist on your branch. Register a placeholder `Standings` route only if the linking config needs it to compile, and say so in the report; `w4-screens` owns the real screen and the merge resolves it.

## Rules

- Approved dependencies for you: `com.squareup.okhttp3:okhttp` (explicit, at the version RN resolves, check with `./gradlew :app:dependencies`) and `com.squareup.okhttp3:mockwebserver` (`testImplementation`, same version). Nothing else. Report the versions.
- Do not edit `contracts/openapi.yaml` or hand-edit `app/src/api/schema.ts`.
- No coordinates, no personal data in notifications beyond the team code and the building (plan 8). Do not log the access token.
- Find the root cause of a failing test before changing code.
- Commit on `feat/w4-realtime`, at least once per logical part. Do not push.

## Verify

`cd app/android && ./gradlew test ktlintCheck` and `cd app && npm run lint && npm run typecheck && npm test`. Break the duplicate drop and the 10-minute limit once each, show the failing tests, revert. On the emulator, post a notification through a debug-only hook, tap it cold and warm, and write what opened. If the emulator cannot run here, say which steps are left.

## Report

- `W4-1 done | verify: <commands> → <summary lines> | commit: <sha>`
- The two break-and-revert results
- The emulator deep-link check, element by element
- OkHttp and mockwebserver versions
- Blocked items, one line each, with your recommendation
