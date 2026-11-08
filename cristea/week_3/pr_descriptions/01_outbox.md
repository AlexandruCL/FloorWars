## W3-0 seam and W3-2 native segment outbox

- **Seam (first commit):** new native module API (`setActiveCheckin`, `getActiveCheckin`, `getPending`, `markSynced`, `markRejected`, `getPendingCount`, `clearPending`, battery methods, `onPendingChanged`) and `outbox/SegmentOutbox.kt`. The three other W3 PRs build on it.
- **Outbox:** Room table `segment_outbox` behind `SegmentOutbox`. `getPending` returns exactly the ten fields of the contract's `Segment` (a test checks the key set). Retention (7 days synced, 30 days rejected), a 5000-row cap that never drops pending rows, idempotent `markSynced` and `markRejected`.
- **New dependencies (approved):** Room 2.8.5 and KSP 2.2.0-2.0.2 (Apache 2.0), Robolectric 4.17 for tests only (MIT). Room 3 was not used because it needs suspend DAOs and the `insert` seam is synchronous.

### Verify
- `cd app/android && ./gradlew test ktlintCheck`: BUILD SUCCESSFUL, 39 tests, 0 failures
- `cd app && npm run lint && npm run typecheck && npm test`: clean, 10 suites, 77 tests
- `npm run generate:api` leaves `schema.ts` unchanged

### Not verified
- The kill-survival test closes and reopens the database; it does not kill the process. On the emulator a force-stop with a pending row kept the row. A real phone run is still open.
- `attempts` is never incremented (no module method covers it).

Tested against the Prism mock and an emulator only, not the real server. Merge this PR first: the other three build on it.
