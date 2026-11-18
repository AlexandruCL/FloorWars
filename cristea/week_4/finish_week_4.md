# Finishing Week 4 (Cristea)

The Week 4 code is done and tested against the Prism mock, Jest and JUnit. What is left needs Ionut's Week 4 server, the two phones, or a merge on GitHub. Do the steps in order and tick each box when it is done.

State on 2026-11-18, with all seven branches merged together on a throwaway branch: Android unit tests 99 run, 0 failed (`./gradlew test ktlintCheck --rerun-tasks`, including the trace-replay gate); Jest 226 of 226 on a cold run in 34 s; lint and typecheck clean.

## 1. Merge the PRs, in this order

Merge each one with **Create a merge commit** (not squash, not rebase), and only when its CI is green.

| Order | Branch | Review |
|---|---|---|
| 1 | `docs/w4-prompt` | none needed (prompt and plan) |
| 2 | `feat/w4-contract` | Ionut |
| 3 | `feat/w4-seam` | none needed |
| 4 | `feat/w4-realtime` | Ionut (socket protocol, `/me/events` use) |
| 5 | `feat/w4-screens` | none needed |
| 6 | `feat/w4-fallback` | none needed |
| 7 | `feat/w4-tuning` | none needed |
| 8 | `docs/w4-finish` | none needed (this file, the tester guide, README, plan) |

The branches already contain each other in this order (realtime is merged into screens, screens into fallback), so each PR merges without conflicts once the ones before it are in. A PR opened before its predecessors merge shows their commits too; that is expected and disappears as they merge.

- [ ] All eight merged, CI green on each

## 2. Turn off the sign-in skip before testers get an APK

`app/src/config/devFlags.ts` has `DEV_SKIP_SIGN_IN = true` since Week 2. It shows a **Skip sign-in (dev)** button in release builds too. A skipped sign-in stores no token, so every request after it fails (check-in says "Could not check in"). Set it to `false` on a new branch and open a PR, or decide to keep it for one more test round.

- [ ] `DEV_SKIP_SIGN_IN` set to `false` and merged, or a decision to keep it written in the README

## 3. When Ionut says his Week 4 server work is deployed

He needs to deploy the WebSocket hub, `game_event`, `GET /v1/me/events`, `POST /v1/landing-scans` and contract 0.8.0 (`reason` on segments, `GET /v1/seasons`). Check from the laptop:

```powershell
curl.exe -i https://api.floorwars.me/healthz
curl.exe -i https://api.floorwars.me/v1/seasons
curl.exe -i https://api.floorwars.me/v1/me/events
curl.exe -i -X POST https://api.floorwars.me/v1/landing-scans
```

`/healthz` answers 200. The other three answer 401 (no token), not 404. A 404 means that part is not deployed yet. A timeout means the laptop can't reach the VM: its firewall lets in team IPs only, and on 2026-11-17 every request from this laptop timed out.

The app already points at `https://api.floorwars.me/v1`; nothing changes in the code.

- [ ] `/healthz` 200, the three paths 401
- [ ] Ionut has printed the landing stickers for both buildings, and told you the points per scan

## 4. Build the release APK (when you decide to)

Build from `main` after step 1, so the APK matches what is merged:

```powershell
git switch main
git pull
cd app
npm ci
cd android
.\gradlew.bat assembleRelease "-PreactNativeArchitectures=arm64-v8a,armeabi-v7a"
```

- The APK is `app\android\app\build\outputs\apk\release\app-release.apk`, signed with the debug key. Don't commit it.
- Week 4 adds `react-native-svg`, Reanimated and worklets, so the first build compiles more native code than before. If the laptop runs out of memory, close the emulator and Metro first.
- Install on both phones: `adb install -r app\android\app\build\outputs\apk\release\app-release.apk`

- [ ] Installed on the SM-S918B
- [ ] Installed on the SM-G985F

## 5. Phone checks (yours, on the real server)

Run them with the two phones, following `cristea/week_4/phone_tests.pdf` (the tester guide), and note the times.

**Plan 9.3, Week 4: phone 2 gets a notification when phone 1 flips a building.**

- [ ] Run 1: SM-G985F's app open on the building's standings. SM-S918B climbs until its team owns the building. The SM-G985F shows a banner `{team} took {building}` and the owner colour changes without a refresh. Tapping the banner opens that building's standings.
- [ ] Run 2: SM-G985F's app swiped away, no check-in. Same climb. The notification arrives through the 15-minute poll. Write down the delay.

**Exit from the plan.**

- [ ] SM-S918B joined team A and SM-G985F team B, both in the active season
- [ ] SM-G985F opened the building's standings, SM-S918B checked in there and climbed until its team owned the building
- [ ] SM-G985F's owner colour flipped live, the notification `A took {building}` arrived, and tapping it opened that building's standings
- [ ] The barometer-less path once on a phone: a debug build with `DEV_FORCE_NO_BAROMETER = true` (local change, not committed), check in, scan a landing sticker, see `Scan counted: +{points} points.`, then the 10-minute cooldown message
- [ ] The Samsung battery steps in the onboarding screen match the settings on both phones (Settings, Apps, FloorWars, Battery, Unrestricted; then Battery, Background usage limits)

Write every surprise from the real server (field names, time zones, auth edges) under "Surprises" at the end of this file.

## 6. Record the two plan 15.3 decisions once Ionut agrees

In `IMPLEMENTATION_PLAN.md` section 15.3, on a docs branch:

- [ ] Accessible contribution mode: the app shows the `points` the server returns for a landing scan and computes none; the value per scan is Ionut's server setting (fill in his value).
- [ ] Third person for the pilot: no (your position on 2026-11-17).

## 7. Send the tester guide

- [ ] Testers get the APK from step 4 and `cristea/week_4/phone_tests.pdf`. Part 5 needs two testers on different teams in the same building; part 6 needs the landing stickers.

## 8. Clean up the worktrees

After step 1, remove the Week 4 worktrees and the throwaway integration branch. Some worktrees show files as modified that differ only in line endings, so `--force` is needed:

```powershell
git worktree remove --force D:/FloorWars-w4/contract
git worktree remove --force D:/FloorWars-w4/seam
git worktree remove --force D:/FloorWars-w4/realtime
git worktree remove --force D:/FloorWars-w4/screens
git worktree remove --force D:/FloorWars-w4/fallback
git worktree remove --force D:/FloorWars-w4/tuning
git worktree remove --force D:/FloorWars-w4/integration
git worktree remove --force D:/FloorWars-w4/finish
git branch -D tmp/w4-integration
```

- [ ] Worktrees removed

## Not done this week, by your decision

- W4-7, the Week 3 service survival numbers in `docs/devices.md`: the service survived on both phones, but adb would not connect to read the numbers. The table stays as it is.
- W4-6 new traces: tuning pass 1 ran on the 21 existing real traces; no new recordings.

## Waiting on Ionut

- Review of `feat/w4-contract` and `feat/w4-realtime`.
- The Week 4 deploy (step 3), the landing sticker token format and the printed stickers, the points per scan.
- Agreement on "no third person for the pilot".

## Surprises

(Fill in during step 5.)
