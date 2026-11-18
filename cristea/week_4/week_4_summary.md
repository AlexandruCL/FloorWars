# Week 4 summary (Cristea, app side)

Goal from the plan: the loop is visible and social. Built 2026-11-17 and 2026-11-18, tested against the Prism mock, Jest and JUnit. The real-server and two-phone checks are in `finish_week_4.md`.

## What was built

| Item | Branch | What it does |
|---|---|---|
| W4-0 | `feat/w4-contract` | Contract 0.8.0-draft: `reason` on `SegmentRecord`, `GET /seasons`, `event_id` required on WS events, `WS /ws` 401 on a bad token. Generated client updated |
| W4-0 | `feat/w4-seam` | The native module methods and the `useGameEvents` hook signature the three UI tracks built against. Also keeps the session-restore App test offline (it called the real server before) |
| W4-1 | `feat/w4-realtime` | One OkHttp WebSocket owned by Kotlin, held while the app is in the foreground or a check-in is active. Bearer token from JS, ping 30 s, backoff 1 s to 60 s with full jitter, `since` replay, dedupe by `event_id`. "Building alerts" notification (high importance) when your team loses a building, at most once per building per 10 minutes. `floorwars://building/{id}` deep link, cold and warm. `GET /me/events` poll in the 15-minute sync job. Silent catch-up after sign-in |
| W4-2 | `feat/w4-screens` | Building standings (SVG stacked bar in team colours, 600 ms Reanimated colour flip on a live `building_flipped`), leaderboards (three tabs, season chips, building picker), in-memory cache with `Last updated {HH:MM}` |
| W4-3 | `feat/w4-screens` | `Verified today: {steps} steps, {metres} m` on Home (verified climbs since local midnight), climb history with a sentence for each rejection reason |
| W4-4 | `feat/w4-fallback` | Scan at the stairs for phones without a barometer: active check-in's building, token sent unchanged, 10-minute local cooldown, `Retry-After` honoured. `DEV_FORCE_NO_BAROMETER` in debug builds only |
| W4-5 | `feat/w4-fallback` | Onboarding once after the team choice: safety, permissions, battery steps for Samsung, Xiaomi and other phones. Reopened from Home |
| W4-6 | `feat/w4-tuning` | Tuning pass 1 on the 21 real traces: precision and recall 1.00 per class, no threshold changed. Recorded in `docs/evaluation.md` |
| W4-8 | `docs/w4-finish` | README, plan, this summary, `finish_week_4.md`, the tester guide `phone_tests.pdf` |

New packages, approved 2026-11-17: `react-native-svg` 15.16.0, `react-native-reanimated` 4.7.1, `react-native-worklets` 0.13.1 (all MIT); OkHttp declared explicitly, MockWebServer for tests.

## Verification

Each branch was re-checked by the coordinating session, not only by the agent that built it. Forced Gradle (`--rerun-tasks`), cold Jest (`--no-cache`).

| Branch | Android | Jest | Break checks (tests fail when the rule is removed) |
|---|---|---|---|
| contract | not affected | 141/141 | generated client matches the contract |
| seam | 64/0 | 141/141 | |
| realtime | 99/0 | 152/152 | dedupe removed: 5 fail; 10-minute limit removed: 1 fails; catch-up mark removed: 7 fail; channel back to default importance: 1 fails |
| screens | as realtime | 193/193 | pending or rejected counted in today's figures: 2 fail |
| fallback | as realtime | 226/226 | cooldown removed: 3 fail |
| tuning | 64/0, replay gate green | not affected | |
| all merged | 99/0 | 226/226 in 34 s | |

Emulator, run by Cristea on 2026-11-18 against Prism: the loss notification posts through the debug receiver (confirmed by Cristea). The other screens were not confirmed one by one on the emulator; they are covered by the phone tests in `finish_week_4.md` and the tester guide.

## Found while testing on the emulator

- The skip-sign-in button stores no token, so check-in fails after it. Open item in `finish_week_4.md`, step 2.
- Prism's random data gives check-ins that are already expired and a new season id on every call, so the app forgets the team choice. A click-through copy of the contract pinned those values; the real server doesn't have this problem.
- The `cityconquest` emulator belongs to another project; this project's is `floorwars_api36`. The laptop's Intel driver is too old for the emulator's Vulkan, so it draws in software and can go black under memory pressure. A cold boot with `-gpu host` fixes it.

## Decisions

All decisions of the week, with dates and reasons, are in section 4 of `week_4_prompt.md` and in the README's "Decisions taken".
