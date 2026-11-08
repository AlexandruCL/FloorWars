# Week 3 summary: Cristea's side

Week 3 in the plan: *walk up real stairs with the phone in a pocket; the segment lands in the DB as `verified`; team score and `building_claim` update; a duplicate upload is a no-op.* On the app side, all the code for that path is built and tested and sits in four pull requests. What is not done is everything that needs a real phone or the deployed server. `finish_week_3.md` lists those steps.

## At a glance

| Item | State | Where |
|---|---|---|
| W3-0 seam and preflight | Done | `feat/w3-outbox-v2` |
| W3-1 live segmenter in the service | Done, tested on traces, not on a phone | `feat/w3-engine-v2` |
| W3-2 native outbox (Room) | Done | `feat/w3-outbox-v2` |
| W3-3 attribution to the active check-in | Done | `feat/w3-engine-v2` |
| W3-4 sync worker, WorkManager job, timeouts | Done, tested against a fake and a proxy, not the real server | `feat/w3-sync-v2` |
| W3-5 status screen | Done, clicked through on the emulator | `feat/w3-sync-v2` |
| W3-6 sign out | Done, clicked through on the emulator; the server revoke call is on its own branch | `feat/w3-signout-v2`, `feat/w3-logout-call-v2` |
| W3-7 gap metric | Counter done; phone checks are Cristea's | `feat/w3-engine-v2` |
| W3-8 QR phone tests | Not run, needs printed codes | `finish_week_3.md` |
| W3-9 integration | Merge proven on a throwaway branch; Wednesday check and exit climb pending | `finish_week_3.md` |

Branch heads when the PRs were pushed (the `-v2` branches, split into small commits): outbox `80a9c35`, engine `4dc2233`, sync `25b7811`, signout `d66b87d`, logout call `bc26712`. The PRs must merge in that order.

## What was verified, and how

Every verify command was re-run by the coordinating session, not taken from the agent reports.

- **Android:** `./gradlew test ktlintCheck` is green on each branch (outbox 39 tests, engine 59, sync 39, signout 39), after a forced re-run of the test task.
- **JS:** `npm run lint`, `npm run typecheck` and `npm test` are green on each branch (77, 82, 116 and 82 tests). `npm run generate:api` leaves `schema.ts` unchanged on each, against the contract 0.6.2-draft that is on `main`.
- **All four merged:** a throwaway branch with the four merged ran green: lint, typecheck, 121 Jest tests, 59 Android tests. Two conflicts needed a hand merge: `build.gradle` (Room and WorkManager lines) and `PlaceholderScreens.tsx`, which the sync PR deletes and the signout PR edits.
- **Replay:** chunked replay equals batch replay on all 45 traces (1 s chunks, 5 s chunks, event by event), plus one long stream of about 2830 s that makes the window trim many times. The trace-replay gate is unchanged. Breaking the emit-once rule makes 9 tests fail.
- **Emulator** (API 36, debug build, Prism with a small proxy for `/checkins` and `/segments`): sign-in and team choice; Home shows the status rows; a check-in started detection (foreground service, barometer) with 90 minutes left; a pending outbox row uploaded by itself with exactly the ten segment fields, an `Idempotency-Key` and the app's `device_id`; a resend came back accepted without points and was marked synced; airplane mode showed "No connection to the server" and the row uploaded after the network came back; a force-stop kept the check-in, the detection and the pending rows; sign-out with a pending row warned, cleared the row and stopped the service.

## Decisions

Cristea decided these on 2026-11-06 and 2026-11-08: Room for the outbox, `stair_prob` a constant 1.0, `clearPending` on sign-out, a wake lock during a check-in, the check-in driving the sensors, attribution by climb start, WorkManager with Headless JS, 429 honouring `Retry-After`, a 422 batch staying pending, a 403 `device-unknown` batch handled like a 422, `device_id` from `getDeviceId()`, 10 s and 20 s timeouts, the 5000-row cap, the gap metric staying local, the status screen extras, Robolectric for tests only, Ionut's review on the contract parts only.

Made during the work by the agents and the coordinating session. Cristea has not reviewed them yet:

- **Window 240 s:** the longest STAIRS climb (180 s) plus the close margin (21.3 s) plus the edge margin (21 s).
- **Expiry grace 201.3 s:** a climb that starts before `valid_until` is stored whole. A climb that starts after it, inside the grace, counts for no check-in.
- **Sampling:** `SENSOR_DELAY_GAME`, sensor batching 5 s, one evaluation pass every 5 s. The 5 s pass is based on a desktop measurement of 16 ms per pass; phone battery cost is not measured.
- **Room 2.8.5, not Room 3:** Room 3 needs suspend DAOs and the `insert` seam is synchronous. The outbox allows main-thread queries so a row is on disk when `insert` returns.
- **Retry-After is not slept on:** on 429 and on a 503 with the header the worker records a not-before time and ends the run, so a headless task does not hang.
- **Idempotency key:** `seg-<count>-<hash of the sorted ids>`, because 100 UUIDs exceed 255 characters.
- **Battery settings:** opens the system list, not the per-app exemption dialog, which Play policy restricts.
- **Sign-out when the pending count cannot be read:** the dialog uses the no-segments wording and does not block the sign-out.
- **Notification shows an end time:** a static notification would show a stale "minutes left".

## Surprises

- **Nothing asked for the activity-recognition permission** in the check-in flow. Only the logger screen did, so on a fresh install detection never started. Fixed: the app now asks after a successful check-in and before `setActiveCheckin`.
- **"Last upload" was overwritten** by a follow-up run that found nothing to upload. Fixed: a run with nothing to upload no longer replaces a real result.
- **A live-window bug:** a climb that started within 21 s of the end of a long gap in sensor delivery was counted as cut by the window edge and never emitted. Found by a new test, fixed by measuring the edge from the trim point.
- **A check-in swap bug:** a check-in swap re-registered the sensors and could drop up to 5 s of events held by the hardware. Fixed: sensors are re-registered only when batching changes.
- **A season rollover leaves users without a team (Ionut, 2026-11-08).** The app only remembered a "team chosen" flag, so after season 2 starts an existing user is let in and every upload comes back `no_team`. Also, a join before the season starts answers 409 `season-not-active`, which the app swallowed as "already joined". Fixed on its own branch (`feat/w3-season-check`): the app stores the joined season id, compares it with `/seasons/active` at start, shows the picker when they differ, and treats only `already-joined` as joined. Checked at app start only.
- **Two PRs passed alone and failed together:** the season-check tests looked for the "Home" heading, which the status screen PR renames "Status". It showed up only on a simulated merge of everything, and the tests now accept either heading.
- **Prism is not enough for the whole path.** Its `/checkins` answers a `valid_until` in the past (the native side correctly ignores an expired check-in, so detection never starts), the "Skip sign-in (dev)" token is rejected with 401, and `POST /segments` returns random ids, so a real drain never matches. A small proxy fixed the first and the last for the emulator pass.
- **The emulator has no step detector**, so it cannot produce a verified climb. The emulator proves the plumbing, not the detection.
- **One Gradle failure that was a JVM crash:** on the signout branch the test task failed with 35 of 39 tests reported and none failing. Five clean re-runs passed. A crash dump (`hs_err_pid*.log`) was left in `app/android/app`: `EXCEPTION_ACCESS_VIOLATION` in `jvm.dll`, JDK 17.0.12 on Windows, at the time of that run. So it was a Java crash on this laptop, not a test or code failure. If it shows up in CI, re-run the job.
- **Ionut's server moved while this week ran:** contract 0.6.0 to 0.7.0 (the steps bound 10 and `POST /auth/logout`, both merged). The branches were rebased twice and the worker already handles the new 503 with `Retry-After`.

## Not done, and why

- **Season check:** `feat/w3-season-check` is written and tested in Jest (5 new tests) but not run on a phone or the emulator, and not against the real server.
- **Wake lock, notification text, stop at expiry, service survival** (screen off, swipe-away, battery saver, no exemption): need both phones. See W3-7 in `finish_week_3.md`.
- **The service is `START_NOT_STICKY`:** after a process kill, detection resumes when the app is opened again. If the phone checks show the service dying, try `START_STICKY` with a restart from the stored check-in, and handle the background-start restriction on Android 12 and later.
- **WorkManager job:** starts a plain service from the background, which Android may refuse on some versions. Not run on a phone.
- **A late permission grant:** if the user denies at check-in and grants later in Android Settings, detection waits for the next check-in or app start.
- **Revoke on sign-out:** the app call is written (`feat/w3-logout-call-v2`, in the Sign out handler, not in `endSession()`, with a 5 s limit and every error swallowed). Not yet run against the real server.
- **Kill-survival of the outbox** was tested with a clean close and reopen, and with a force-stop on the emulator; a kill during a write is not tested.
- **`attempts`** in the outbox is never incremented.
- **The Wednesday check and the exit climb** wait for the deployed server and a real phone.
