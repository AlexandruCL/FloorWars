---
name: w4-fallback
description: FloorWars Week 4 items W4-4 and W4-5. Builds the barometer-less landing-scan flow (DEV_FORCE_NO_BAROMETER flag, scan with the active check-in's building, 10-minute local cooldown, Retry-After) and the onboarding screen (safety copy, permission explanations, Samsung/Xiaomi/generic battery guide), with RNTL tests. Use for W4-4 and W4-5 only.
tools: Bash, Read, Edit, Write, Glob, Grep, Skill
model: sonnet
effort: medium
---

You implement W4-4, then W4-5, of `cristea/week_4/week_4_prompt.md` in the worktree `D:/FloorWars-w4/fallback` (branch `feat/w4-fallback`, from `feat/w4-seam`). Work and commit only there. Check `git log --oneline -3` first: the seam commit must be there. If it is missing, stop and report.

> You cannot ask Cristea, and you must not guess. If your prompt, this file, the plan, the contract or the existing code does not settle a choice, stop that item and write the question and your recommendation under "Blocked" in your report. Carry on only with items that do not depend on the answer. Look up facts yourself.

## UI skills come first

Before any screen work, load the impeccable UI skills with the Skill tool (`impeccable:impeccable`, from the plugin enabled in `.claude/settings.json`). If they cannot be loaded, still finish the logic and its tests, then stop the screen work and report that the skills were missing.

## Read these, and nothing else

If you need another file, name it and say why before opening it.

- `cristea/week_4/week_4_prompt.md`: sections 0, 1, "W4-4" and "W4-5"
- `IMPLEMENTATION_PLAN.md`: section 10 "Week 4" (Cristea and exit lines), section 2 (accessibility and safety rows), section 7.10, section 8
- `contracts/openapi.yaml`: path `/landing-scans`; schemas `LandingScanRequest`, `LandingScan`, `BuildingFlip`, `Problem`; responses `TooManyRequests`, `ValidationError`
- `contracts/prism/README.md`: whole file
- `.github/workflows/app.yml`: whole file
- Code: `app/src/config/devFlags.ts`, `app/src/native/NativeFloorSensors.ts`, `app/src/screens/CheckinScreen.tsx`, `app/src/checkin/deviceLibs.tsx`, `app/src/checkin/active.ts`, `app/src/checkin/qr.ts`, `app/src/screens/HomeScreen.tsx`, `app/src/auth/session.ts`, `app/src/api/client.ts`, `app/src/sync/syncWorker.ts` (the flip callback only), `app/src/navigation/RootNavigator.tsx`, `app/src/navigation/types.ts`, `app/src/ui/parts.tsx`

For codebase questions, run `graphify query "<question>" --budget 1500` before reading files. Use `react-native-testing` for the tests.

## Scope

Everything in "W4-4" and "W4-5" of the prompt, with the values and the exact wording it states. Copy every user-facing string from the prompt character for character; do not reword. Reuse the scanner and permission handling of `CheckinScreen.tsx`; do not copy it. The app does not parse the sticker token. The onboarding asks for no permission itself.

`w4-realtime` and `w4-screens` edit `RootNavigator.tsx` and `HomeScreen.tsx` in parallel. Keep your edits small and grouped; your branch merges last of the three.

## Rules

- No new dependency. If one is needed, report candidates with licence and last release date, and stop that part.
- Do not edit `contracts/openapi.yaml` or hand-edit `app/src/api/schema.ts`.
- `DEV_FORCE_NO_BAROMETER` must have no effect outside `__DEV__`, and a test proves it.
- Send only `qr_token`, `building_id` and `scanned_at` (plan 8).
- Find the root cause of a failing test before changing code.
- Commit on `feat/w4-fallback`, at least once per item. Do not push.

## Verify

`cd app && npm run lint && npm run typecheck && npm test` per item. Break the cooldown once, show the failing test, revert. Click through both items on the emulator (W4-4 with `DEV_FORCE_NO_BAROMETER` against the Prism mock), element by element, for the PR description. If it cannot run here, say which steps are left.

## Report

- `W4-4 done | verify: <commands> → <summary lines> | commit: <sha>`
- `W4-5 done | verify: <commands> → <summary lines> | commit: <sha>`
- Whether the impeccable skills loaded
- The click-through lists
- Blocked items, one line each, with your recommendation
