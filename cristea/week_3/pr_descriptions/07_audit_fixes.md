## Week 3 audit fixes

Fixes for the audit of PRs #62 to #68 against the Week 3 plan. This branch is based on the merged state of those PRs (it merges their branches), so until they are in `main` the diff also shows their commits; after that it is only the fixes below, one commit each.

| # | Problem found | Fix |
|---|---|---|
| 1 | After a 403, 422 or Retry-After the sync worker stayed blocked until the app was killed, even after a sign-out and sign-in | The triggers' stop function (called when the user leaves the signed-in stage) resets the sync state. New test fails without it. |
| 2 | The module resumed detection in its constructor; in the WorkManager background process Android 12+ refuses a foreground service start and the exception escaped | The start is wrapped in a try/catch for `IllegalStateException`; detection resumes at the next foreground start |
| 3 | A climb open at sign-out was flushed into the outbox after `clearPending()`, so the next user on the phone inherited it | `clearActiveCheckin` (only called by sign-out) stops detection and drops the open climb; `endSession` now stops detection before clearing rows. New test fails on the old order. |
| 4 | The season was checked only at app start, so a season that rolled over while the app was open lost climbs as `no_team` | The season is also checked each time the app returns to the foreground. New test fails without it. |
| 5 | The 15-minute job started the whole React Native runtime even with nothing to upload | The job starts it only when the outbox has pending rows |
| 6 | `ActiveCheckinStore` (the check-in that survives a restart) had no test | Robolectric test: save, load, expiry removal, clear, replace. Breaking the expiry removal fails exactly one test. |
| 7 | The check-in waited for system permission dialogs before it reached the native side and before "Checked in" showed | The check-in is stored natively first; the dialogs run without holding up the screen, and a grant sends it again so detection starts. Tests fail if the order is reversed. |
| 8 | The idempotency key used a hand-written 53-bit hash, but the server treats the key as informational | `seg-<count>-<first id>-<last id>`: about 17 lines fewer |
| 9 | The `attempts` column is never written | **Left as it is on purpose**: it will be used later |

### Verify
- `cd app && npm run lint && npm run typecheck && npm test`: clean, 16 suites, 141 tests
- `npm run generate:api`: `schema.ts` unchanged
- `cd app/android && ./gradlew test ktlintCheck`: BUILD SUCCESSFUL, 64 tests, 0 failures (5 new)
- Breaking fixes 1, 3, 4, 6 and 7 makes the matching tests fail (each checked once, then restored).

### Not covered
- Fix 2 and the service side of fix 3 are native code with no JVM test: they need a phone (swipe the app away, wait for the 15-minute job; sign out with a climb in progress).
- Fix 3: the stop intent and `clearPending` are two separate calls, so a segment emitted in the few milliseconds between them could still be written. It needs a segment to close in that window.
- Fix 7: when activity recognition is already granted, the check-in is sent to the native side twice (harmless: the service treats the same id as the same check-in).

### Open question for Ionut (audit finding 4)
When a user has not joined the running season, the server answers `no_team` and the app marks the climb rejected for good. Can a rejected `no_team` segment be re-sent with the same id after the user joins and be accepted? If yes, the app should keep `no_team` rows pending instead of marking them rejected. Not changed here.
