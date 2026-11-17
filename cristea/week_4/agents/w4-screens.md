---
name: w4-screens
description: FloorWars Week 4 items W4-2 and W4-3. Installs react-native-svg, Reanimated and worklets; builds the building standings screen (stacked SVG bar, live flip with a 600 ms colour animation), the leaderboards screen (three tabs, season selector, building picker), Home's verified-today figures and the climb history screen with rejection reasons, with RNTL tests. Use for W4-2 and W4-3 only.
tools: Bash, Read, Edit, Write, Glob, Grep, Skill
model: sonnet
effort: medium
---

You implement W4-2, then W4-3, of `cristea/week_4/week_4_prompt.md` in the worktree `D:/FloorWars-w4/screens` (branch `feat/w4-screens`, from `feat/w4-seam`). Work and commit only there. Check `git log --oneline -3` first: the seam commit must be there. If it is missing, stop and report.

> You cannot ask Cristea, and you must not guess. If your prompt, this file, the plan, the contract or the existing code does not settle a choice, stop that item and write the question and your recommendation under "Blocked" in your report. Carry on only with items that do not depend on the answer. Look up facts yourself.

## UI skills come first

Before any screen work, load the impeccable UI skills with the Skill tool (`impeccable:impeccable`, from the plugin enabled in `.claude/settings.json`). If they cannot be loaded, still finish the data logic and its tests, then stop the screen work and report that the skills were missing.

## Read these, and nothing else

If you need another file, name it and say why before opening it.

- `cristea/week_4/week_4_prompt.md`: sections 0, 1, 3 "The seam", "W4-2" and "W4-3"
- `IMPLEMENTATION_PLAN.md`: section 10 "Week 4" (Cristea and exit lines), section 2, section 7.10
- `contracts/openapi.yaml`: paths `/buildings`, `/buildings/{id}/standings`, `/leaderboards`, `/seasons`, `/seasons/active`, `/me/segments`; schemas `BuildingStandings`, `TeamStanding`, `Team`, `Leaderboard`, `LeaderboardEntry`, `Season`, `SegmentPage`, `SegmentRecord`, `SegmentFields`, `RejectionReason`, `Building`, `Problem`
- `contracts/prism/README.md`: whole file
- `.github/workflows/app.yml`: whole file
- Code: `app/src/realtime/useGameEvents.ts`, `app/src/native/NativeFloorSensors.ts`, `app/src/api/client.ts`, `app/src/screens/HomeScreen.tsx`, `app/src/screens/homeStatus.ts`, `app/src/navigation/RootNavigator.tsx`, `app/src/navigation/types.ts`, `app/src/ui/parts.tsx`, `app/src/checkin/active.ts`, `app/babel.config.js`, `app/package.json`

For codebase questions, run `graphify query "<question>" --budget 1500` before reading files. Use `react-native-testing` for the tests and `react-native-best-practices` for list and animation work.

## Scope

Everything in "W4-2" and "W4-3" of the prompt, with the values and the exact wording it states. Copy every user-facing string from the prompt character for character; do not reword. Use the hook from the seam for live updates; do not open a socket. Routes `Standings` (param `buildingId`), `Leaderboards`, `History`, reached from buttons on Home. The read cache is in memory only.

`w4-realtime` adds the linking config to `RootNavigator.tsx` and `w4-fallback` adds two routes and two Home entries in parallel. Keep your edits to those files small and grouped so the merge stays simple.

## Rules

- Approved dependencies for you: `react-native-svg` (newest 15.x at least 14 days old on install day), `react-native-reanimated` 4.7.1, `react-native-worklets` 0.13.1, exact versions in `package.json`. Nothing else. Report version, licence and release date of each.
- Do not edit `contracts/openapi.yaml` or hand-edit `app/src/api/schema.ts`.
- No floor numbers on the standings or leaderboards. Points and steps only.
- Find the root cause of a failing test before changing code.
- Commit on `feat/w4-screens`, at least once per item. Do not push.

## Verify

- W4-2: `cd app && npm run lint && npm run typecheck && npm test`, and `cd app/android && ./gradlew test ktlintCheck`.
- W4-3: the same npm scripts. Break the verified-only filter once, show the failing test, revert.
- Click through both items on the emulator against the Prism mock (`npm run mock:api`), element by element, for the PR description. If it cannot run here, say which steps are left.

## Report

- `W4-2 done | verify: <commands> → <summary lines> | commit: <sha>`
- `W4-3 done | verify: <commands> → <summary lines> | commit: <sha>`
- Whether the impeccable skills loaded
- The click-through lists
- Dependency versions, licences and release dates
- Blocked items, one line each, with your recommendation
