# Finishing Week 3: the manual steps

The Week 3 code is done and in four pull requests. What is left needs people, the deployed server and real phones: opening and merging the PRs, the server deploy, the phone checks, the printed entrance codes, and the first real climb. This file lists those steps in order. Tick each box when it is done.

Commands are for PowerShell on Windows, run from the repository root unless a step says otherwise. The summary of what was built and verified is `cristea/week_3/week_3_summary.md`.

## Where things stand (2026-11-08)

| Branch | Items | Head | State |
|---|---|---|---|
| `feat/w3-outbox` | seam, Room outbox | `932ee79` | pushed, PR not opened yet (the GitHub CLI is not installed on the laptop) |
| `feat/w3-engine` | live segmenter, check-in attribution, gap counter | `8b13451` | pushed, PR not opened, includes the outbox commits until that PR merges |
| `feat/w3-sync` | sync worker, WorkManager job, status screen | `da3f845` | pushed, PR not opened, includes the outbox commits |
| `feat/w3-signout` | sign out | `956f9d0` | pushed, PR not opened, conflicts with the sync PR on Home (see step 1) |
| `docs/w3-finish` | this file, the summary, the tester guide, README and plan updates | n/a | pushed with the PR for it |

All four branches are green on Android tests, ktlint, lint, typecheck, Jest and the generated-client check, against the contract on `main` (0.6.2-draft). They have only been tested against the Prism mock and an emulator, never the real server.

## Step 1. Open and merge the pull requests, in this order

Open each PR on GitHub with the compare link, base `main`, and paste the body from `cristea/week_3/pr_descriptions/`. Ask Ionut for review on the parts that touch the contract (`/segments`, `/checkins`).

- [ ] `feat/w3-outbox`: https://github.com/AlexandruCL/FloorWars/pull/new/feat/w3-outbox. Body: `pr_descriptions/01_outbox.md`.
- [ ] `feat/w3-engine`: https://github.com/AlexandruCL/FloorWars/pull/new/feat/w3-engine, after the outbox PR is merged. Body: `02_engine.md`. Update the branch from `main` first (**Update branch** on the PR page, or a rebase).
- [ ] `feat/w3-sync`: https://github.com/AlexandruCL/FloorWars/pull/new/feat/w3-sync, after the outbox PR. Body: `03_sync.md`.
- [ ] `feat/w3-signout`: https://github.com/AlexandruCL/FloorWars/pull/new/feat/w3-signout, **after the sync PR**. Body: `04_signout.md`. It conflicts there, because the sync PR deletes `app/src/screens/PlaceholderScreens.tsx` and the signout PR edits it. Rebase onto `main`, then:
  - keep the deletion of `PlaceholderScreens.tsx`;
  - in `app/src/screens/HomeScreen.tsx` add the imports `Alert` (from `react-native`) and `endSession` (from `../auth/session`), the `confirmSignOut` function from the old `PlaceholderScreens.tsx`, and `<Button title="Sign out" onPress={confirmSignOut} secondary />` as the last child of `<Screen>`;
  - in `app/__tests__/signout.test.tsx` wait for `Status` instead of `Home`, and use `mockResolvedValue` (not `Once`) for `getPendingCount`, because Home reads it too.
  - The resolved version is on a local throwaway branch (`tmp/w3-integ`) if you want to compare; the Jest run on it had 121 tests green.
- [ ] CI is green on each: `android unit tests and trace replay` and `lint, typecheck, test, API client`. If the Android test task fails with a dead test worker and no failing test (it happened once locally), re-run it once and look at the worker log before changing code.
- [ ] After each merge, bring your main up to date: `git switch main; git pull`.

## Step 2. Ask Ionut for these

Send him the list below. The state of each was checked against his pushes on 2026-11-08.

| # | Item | State | App default until it is done |
|---|---|---|---|
| 1 | The server is up and deployed: `healthz` answers, and `POST /v1/segments` and `GET /v1/buildings` exist | `curl.exe https://api.floorwars.me/healthz` timed out on 2026-11-08 (no answer, not a 404). His runbook note says a timeout usually means a deallocated VM. The README still says "not yet deployed". | Build and test against the Prism mock |
| 2 | Steps per metre upper bound 10 (instead of 8) | **Merged** to `main` (#59, contract 0.6.2-draft). Waits for the deploy. | A pocket climb rejected as `pressure_steps_mismatch` means the fix is not deployed, not that the app is wrong |
| 3 | `overlap` rejection reason | **Solved**: in the contract since 0.6.0-draft | The app stores any reason string |
| 4 | Revoke on sign-out | `POST /v1/auth/logout` is on his branch `feat/w3-auth-logout` (contract 0.7.0-draft), not merged | Local sign-out only; after it merges, regenerate the client and call it best-effort from `endSession()` in a new branch and PR |
| 5 | Printed entrance codes for both buildings | **Open.** The generator is `tools/qr/make_entrance_qr.py`; codes must be valid on the test day (`--days` at most 31). Ask for an expired code and a code of another building too. | W3-8 rows wait |
| 6 | A gap-metric endpoint before the pilot | **Open**, not urgent | The metric stays on the phone |

- [ ] Message sent to Ionut.
- [ ] `healthz` answers: `curl.exe -i https://api.floorwars.me/healthz`
- [ ] `POST /v1/segments` exists on the server. A request without a token must answer 401, not 404: `curl.exe -i -X POST https://api.floorwars.me/v1/segments`
- [ ] The running release is the Week 3 one. Ionut can tell you (`cat /srv/floorwars/current` on the VM).

## Step 3. Build the tester app

The release APK carries its own JavaScript and talks to `https://api.floorwars.me/v1`, so it needs the server from step 2. Build from `main` after the four PRs are merged, so the APK matches what is merged.

```powershell
git switch main
git pull
cd app
npm ci
cd android
.\gradlew.bat assembleRelease "-PreactNativeArchitectures=arm64-v8a,armeabi-v7a"
```

- The APK is `app\android\app\build\outputs\apk\release\app-release.apk`. It is signed with the debug key. Do not commit it.
- Week 3 adds Room, KSP and WorkManager, so the first build is slow again.
- Install on both phones: `adb install -r app\android\app\build\outputs\apk\release\app-release.apk`
- Before testing, on each phone: allow notifications and physical activity when the app asks (it asks right after a check-in succeeds).

- [ ] `app-release.apk` built
- [ ] Installed on the SM-S918B
- [ ] Installed on the SM-G985F

## Step 4. W3-7: service survival and the gap metric (both phones)

Eight rows: two phones times four states. For each row: note the battery percentage, check in (the service now runs for 90 minutes plus a 3-minute grace), leave the phone in the state below in a pocket for ten minutes, then climb one flight of stairs, then open the app and read the **Status** screen, and note the battery percentage.

| State | How |
|---|---|
| Screen off | Press the power button after the check-in |
| App swiped away | Check in, open recents, swipe the app away, leave the screen on or off as you like |
| Battery saver on | Turn on battery saver in the quick settings before the check-in |
| Battery optimisation not exempt | The default. Screen off for 20 minutes instead of 10 |

Read after each row:

- the **Status** screen: Detection, Check-in minutes left, Last segment, Waiting to upload;
- the gap metric, which is not on the screen. Read it from logcat with the phone on USB: `adb logcat -d -s FloorSensors`. The line `getStatus {...}` carries `longest_gap_s` and `gaps_over_threshold` (Home reads status about every 30 seconds), and `gap session: longest=... over5.0s=...` is printed when the session ends.

Write the results in `docs/devices.md`, in the section "Week 3 service survival" (the table is there, empty). If the service dies in any state, write the state and the logcat line (`adb logcat -d | Select-String FloorSensors`) and tell Claude: the fix is `START_STICKY` with a restart from the stored check-in, not a guess.

- [ ] SM-S918B: four rows filled
- [ ] SM-G985F: four rows filled
- [ ] Battery cost noted per row (this is the real cost of the wake lock and the 5 s evaluation pass)

## Step 5. W3-8: the entrance-QR phone tests (needs Ionut's printed codes)

Carried over from Week 2. Do them with the release APK.

| # | Do | Expect |
|---|---|---|
| 5 | **Check in**, **Scan entrance code**, allow the camera, point at the printed code | "Checked in: Facultatea de ..., 90 min left" (the app rounds minutes up) and **Done**. If `GET /v1/buildings` is not deployed the app shows "Building N" instead of the name: record that as pending, not as a failure |
| 8 | Phone settings, Apps, FloorWars, Permissions: Camera **Don't allow**, then **Scan entrance code**, and tap **Don't allow** if Android asks again | "Camera access is off. Allow it in Settings, or check in with your location." and **Open Settings** opens the app's settings |
| 10 | Camera allowed again, airplane mode on, scan the printed code | "Could not check in. Check your connection, wait a moment, and try again." |
| extra | An expired code and a code of another building, if Ionut has one | Record the messages |

- [ ] Rows 5, 8 and 10 pass
- [ ] Results written in the PR description of the sync PR or in a short note under `cristea/week_3/`

## Step 6. The Wednesday check and the exit climb

Only when steps 2 and 3 are done.

1. Check in with the phone, put it in a pocket, and walk up a real staircase (at least 2 m of ascent, about 4 to 10 steps per metre; two floors is plenty).
2. Wait a minute, open the app. **Waiting to upload** shows 1, then the upload runs by itself (or press **Sync now**).
3. Check on the server (ask Ionut or use `tools/e2e/e2e_check.py`): the segment is `verified`, the team score went up and the `building_claim` changed.
4. **Duplicate test.** Check in again, climb, and while the segment is still pending: put the phone in airplane mode, wait for the upload to fail, turn airplane mode off and swipe the app away right as the upload runs (you will not hit the exact moment every time). Reopen it. The same segment may be sent again. Expected: accepted again and **no points added twice**. The emulator already showed the app side of this (a resend came back accepted without points and was marked synced).
5. Run `tools/e2e/e2e_check.py` once to confirm the server still matches the contract. With `--upload` it uploads fake segments too (see `tools/e2e/README.md`). Rerunning `--upload` on the same account within 3 minutes fails with `rejected as overlap`; wait or use another account.

Write down anything that surprised you (field names, time zones, auth edges, rounding).

- [ ] The segment landed as `verified`
- [ ] Team score and `building_claim` updated
- [ ] A repeated upload added no points
- [ ] `tools/e2e/e2e_check.py` passed

## Step 7. Write down the results

1. Put the step 4, 5 and 6 results into `docs/devices.md` and a short note under `cristea/week_3/` (or the sync PR description).
2. Anything that failed: tell Ionut with the time it happened (the server logs are by time).
3. When Ionut's `feat/w3-auth-logout` has merged, open a new branch and PR: regenerate the client (`npm run generate:api` in `app/`), call logout best-effort in `endSession()`.
4. Update the README status row "App, week 3" from "Code done" to done, with the date. Update the PR descriptions that said "tested against the Prism mock only".

## If something goes wrong

| Problem | What to do |
|---|---|
| **Status** says Detection "Not running" right after a check-in | The sensor permission was denied. Phone settings, Apps, FloorWars, Permissions: allow Physical activity and Notifications, then check in again |
| Check-in works but the notification does not appear | Notifications are off for the app (Android 13 and later). Turn them on in the app settings |
| **Waiting to upload** keeps growing, red text on Status | Read the text. "No connection" retries by itself. "The server refused an upload" (422) or "This phone is not registered" (403) means an app or server bug: the rows stay pending, nothing is lost, send the screenshot and the time |
| A climb in the pocket is rejected as `pressure_steps_mismatch` | The server still has the old 8 steps-per-metre limit. Ask Ionut to deploy 0.6.2 |
| A climb never appears as pending | Check the **Status** screen: a climb under 2 m, without steps, or not matching the stair rule is not stored. Elevators are dropped on purpose |
| The service dies with the screen off | Write the state and the logcat line in `docs/devices.md`, then tell Claude. Also try the **Open battery settings** button on Status and set the app to unrestricted |
| `curl` to `healthz` hangs | Nothing answered: see "`/healthz` times out" in `docs/runbook.md` (VM state, DNS, NSG, containers) |
| `adb` does not list the phone | USB debugging is off, or the cable is charge-only |

## Open after Week 3

- The service is `START_NOT_STICKY`: after a process kill it comes back only when the app is opened.
- A late grant of the sensor permission in Android Settings does not start detection until the next check-in or app start.
- The 15-minute WorkManager job starts a service from the background; some Android versions may refuse it.
- The outbox column `attempts` is never incremented.
- Flip events from `/segments` go to a callback and are not shown yet (Week 4).
- The gap metric needs an upload endpoint before the pilot.
