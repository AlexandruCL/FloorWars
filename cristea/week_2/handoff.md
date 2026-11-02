# Week 2 handoff (2026-11-02)

Resume Week 2 from here, on a machine with a running Android emulator. The task list is `cristea/week_2/week_2_prompt.md`. Paths there say `D:\FloorWars`; use your local checkout instead.

## Before you start

- `.claude/` is gitignored, so the project agents (`w2-segmenter`, `w2-classifier`, `w2-replay-harness`, `w2-auth-ui`, `w2-checkin-ui`, `w2-preflight`) are not in git. Copy `.claude/agents/` from the old machine, or the Agent tool won't list them. Restart the session after copying.
- The impeccable UI skills are a global plugin (`impeccable:impeccable`), not project skills. Nothing to copy.
- The SDK needs JDK 17+, `platforms;android-37.0` (compileSdk 37 is published as `android-37.0`), `build-tools;37.0.0`, `ndk;27.1.12297006`, and CMake (`cmake;3.22.1` was planned). Gradle wrapper 9.4.1.
- Create one worktree per branch, e.g. `git worktree add ../FloorWars-w2/<name> <branch>`, then `npm ci` in each `app/`.

## Branch status (all pushed, no PRs opened)

| Branch | Items | Head | State |
|---|---|---|---|
| `feat/w2-segmenter` | W2-1 to W2-4 | `1650528` (= main) | **Not started.** Blocked here on no JDK/SDK. |
| `feat/w2-auth` | W2-5 | `16acc3d` | Code and Jest done. Click-through in the app not done. |
| `feat/w2-checkin` | W2-6 | `1f9ba38` + this file | Branched from `feat/w2-auth`. Code, Jest and libraries done. **Android build never ran.** |

## Verified here

| Item | Command | Result |
|---|---|---|
| W2-0 Node baseline (main) | `cd app && npm run lint && npm run typecheck && npm test` | lint 0, tsc 0, 6 suites / 16 tests pass |
| W2-0 Android baseline (main) | `cd app/android && ./gradlew test` | **Not recorded.** No JDK at first; the run was stopped before it finished. |
| W2-5 (`16acc3d`) | lint, typecheck, Jest, `npm run generate:api` + `git diff --exit-code app/src/api/schema.ts` | lint 0, tsc 0, 8 suites / 36 tests, schema clean |
| W2-6 (`1f9ba38`) | lint, typecheck, Jest | lint 0, tsc 0, 9 suites / 71 tests |

## Next steps, in order

1. On `main`: `cd app/android && ./gradlew test`. Record it as the W2-0 Android baseline.
2. On `feat/w2-checkin`: `npm ci`, then `cd app/android && ./gradlew assembleDebug`. This is the first native build with Vision Camera 5 (Nitro). Fix build issues here before anything else. Then `npx react-native run-android` on the emulator.
3. Track A: run `w2-segmenter` (W2-1), then `w2-classifier` (W2-2), then `w2-replay-harness` (W2-3, W2-4), one after another on `feat/w2-segmenter`. Re-run `./gradlew test` yourself after each.
4. Click-through against the Prism mock on the emulator: `npx @stoplight/prism-cli@5.14.2 mock contracts/openapi.yaml --port 4010 --dynamic`, and point `API_BASE_URL` at `http://10.0.2.2:4010` locally (do not commit that). Record it element by element for the W2-5 and W2-6 PR descriptions. W2-6 steps: Home → "Check in"; idle shows "Scan entrance code" and "Use my location" with no permission prompt yet; scan → camera prompt (allow: camera box + Cancel; deny: error + "Open Settings"); valid code → "Checking in..." → "Checked in: Building X, N min left" + Done; 403 `qr-expired` / `qr-invalid` → their messages; location → prompt → "Finding your position..." → success, or `outside-geofence` message; Prism stopped → "Could not check in..." with retry. Prism's `Prefer: code=403` does not pick a Problem type, so the examples must carry the `urn:floorwars:problem:*` slugs.
5. W2-7: staging URL from Ionut, then PRs. The user said not to open PRs from the previous session; ask before opening them.

## Decisions

- **Libraries (approved by Cristea):** `react-native-vision-camera` 5.2.4, `@react-native-community/geolocation` 3.4.0. Vision Camera 5 also needs `react-native-nitro-modules` 0.37.1 and `react-native-nitro-image` 0.15.2 (peer deps), and `react-native-vision-camera-barcode-scanner` 5.2.4, because v5's own object output reads codes on iOS only. That plugin was added without separate approval; confirm or swap it.
- **Location permission:** built-in `PermissionsAndroid`, then one `getCurrentPosition` (high accuracy, 15 s timeout, 10 s max age).
- **Manifest:** `CAMERA`, `ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION` (Android 12+ needs both location ones).
- **Adapter:** `app/src/checkin/deviceLibs.tsx` implements `CheckinDeps`; tests inject fakes, and `jest.setup.js` mocks the three native modules.
- **Refresh:** one shared in-flight refresh promise; `/auth/*` never triggers refresh; a 401 from `/auth/refresh` signs out and clears the Keychain; network errors and 5xx keep the session.
- **Design context (assumed by the W2-5 agent, confirm):** light warm theme, one orange accent, system fonts. Styles live in `app/src/ui/parts.tsx`.
- **Local expiry check on QR:** the app trusts the phone clock to show "expired" without a network call (marked `shortcut:` in code).

## Blocked (default in brackets)

- Staging URL from Ionut. `API_BASE_URL` is still `https://api.example.invalid/v1`. [Leave it until Ionut sends it.]
- Contract: `accuracy_m` on geofence check-in is accepted by the server but missing from `contracts/openapi.yaml`; the `urn:floorwars:problem:*` type URIs are undocumented. [Ask Ionut for a contract PR; app sends lat/lon only.]
- Refresh-token reuse and expiry both return the same 401. [Sign out on both.]
- No sign-out button or authenticated screen beyond Home. [Add with the Home work.]
- `Team` has no display name in the contract. [Show faculty code and colour.]
- W2-4 real-data gate: not run yet.

## Phone checks for Cristea (not claimed)

- Sign up with e-mail and OTP, pick a team.
- Scan an entrance QR and see "Checked in: Building X, N min left".
- Deny camera, then location: each shows its error and the Settings button works.
- Check in by location near and away from a building.

## Old machine notes

- The old machine had no CPU virtualisation (SVM off in BIOS), so no emulator. Android Studio downloads failed twice on a slow link. Nothing from that machine is needed here.
- `npm audit` reports existing high issues in `body-parser` and `deepmerge` (React Native CLI tooling). Not new, not fixed.
