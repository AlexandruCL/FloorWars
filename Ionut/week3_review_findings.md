# Week 3 review findings (local notes, not for GitHub)

Written for: Ionut, to decide and fix these later today.
Source: independent review by `w3-f` of main at d2794c8 (no code changed). Line numbers are from that review.
Delete this file locally after the fixes are merged.

## Decisions already made

- **1 (high), late uploads:** count each climb against the time window on both sides, so an out-of-order upload is checked against the climbs before and after it. Accepted trade-off: an honest late upload can lose some points.
- **3, overlapping climbs:** reject a climb whose time window overlaps one of the user's verified climbs. This needs a new rejection reason and a contract change.
- **5, 6, 7, 11 (leaderboards):** solve today, not in Week 5.

## Plan for today

1. **Quick fixes:** findings 2, 4, 8, 10, 13, 17.
2. **Scoring:** findings 1 and 3 (with the new reason and the contract change).
3. **Leaderboards:** findings 5, 6, 7, 11.
4. Then 9 and 14, if time allows. The rest can wait.

## Findings

### Cheating with points

**1 (high). Newest-first uploads bypass the caps.** `service.py:173-175, 206-208`; `repository.py:131-132`.
- What happens: the rules check the 10-minute step cap and the 60-minute window looking backward only. A user can send single-climb batches that are each older than the last, and each counts as fresh. Reviewer's estimate: 60 uploads give about 25,200 points, against about 1,950 for honest play in an hour.
- Fix (decided): count verified steps on both sides of `started_at` under the user lock. Amend spec rule 8 to say so.

**3. Same climb counted twice under new ids.** `service.py:165-177`.
- What happens: nothing checks whether a new climb overlaps one the user already has.
- Fix (decided): reject a climb whose `[started_at, started_at + duration)` overlaps a verified climb of the same user, checked under the lock. New rejection reason (name to be chosen, e.g. `overlap`). Update the contract, regenerate the client, and update spec section 4.

**12 (low). Second device resend gets the wrong answer.** `service.py:173-176, 189-193`.
- What happens: a resend from a different device can get `rate_limit` and a fraud flag. Spec section 5 says `no_checkin` with no flag.
- Fix: check `(id, started_at)` right after the receipt lookup, before the rules.

**15 (low). Device sharing and deadlocks.** `service.py:217, 265`; `repository.py:77-88`.
- What happens: a shared device id allows a receipt race between users, and two colluding users can deadlock.
- Fix: insert the receipt first with `RETURNING`, and sort on `(started_at, id)`. Changes decision 1 (receipts per user, not per device).

### Crashes and failed batches

**2 (medium). A tiny stair value fails the whole batch.** `service.py:159`.
- What happens: `stair_prob = 1e-50` underflows in the database and the batch returns 500 on every retry (confirmed in psql).
- Fix: guard it in the rules, `rules.storable_real(item.stair_prob)`, and add a test.

**13 (low). A huge building id crashes standings.** `api/v1/buildings.py:65, 68`.
- Fix: limit the id to 2147483647 here and on the leaderboard ids for consistency.

**17 (low). A saved upload can return an error.** `service.py:245`.
- What happens: if the leaderboard update fails after the commit, the request returns 500 even though the upload was saved.
- Fix: catch the exception, log it with `logger.exception`, and return success.

**19 (low). NaN stored in rejected rows.** `rules.py:157-158`.
- Fix: store a finite sentinel instead.

### Leaderboards

**4 (medium). Any user can force full-season rebuilds.** `api/v1/leaderboards.py:86-88`; `leaderboards.py:129-131, 153`.
- What happens: buildings with no points never get a key, so every read repeats the full rebuild (4 SQL queries, 3 of them full scans, about 73 Valkey calls). There's no rate limit.
- Fix: rebuild only when the key is missing. Return 404 for an unknown season or building, and an empty list for a building with no points.

**5 (medium). Rebuild racing an upload.** `leaderboards.py:143-154`; `service.py:288`.
- What happens: a rebuild that runs while an upload is being scored can double-count or lose points, and the wrong totals stay.
- Fix (today): a Valkey lock (`SET NX` with a short expiry) around the rebuild, and the upload's update waits on the same lock. A periodic rebuild narrows the damage but doesn't remove it.

**6 (medium). Partial board served as complete.** `leaderboards.py:68-70, 102`.
- What happens: after Valkey data loss, the next upload recreates the key with only the new points. Since the key now exists, the rebuild never runs.
- Fix (today): a marker key `fw:lb:s{season}:built`, set by the rebuild. Reads check it and rebuild if it's missing. Uploads skip updating a board that has no marker.

**7 (medium). Failed updates are never repaired.** `service.py:240-246`; `leaderboards.py:68-70`.
- What happens: one Valkey error skips the remaining boards and all flips, and the three updates per segment aren't atomic. The resend answers from the receipt, so the update is never retried.
- Fix (today): a separate `try` for flips, the per-segment updates in one `MULTI/EXEC` transaction, and on failure mark the season "needs rebuild" (the marker from 6 is reused). The next read rebuilds it.

**11 (future). Deleted users stay on boards.** `leaderboards.py:68, 153`; `api/v1/leaderboards.py:155-156`.
- Fix (today, if simple): remove the user from the season's boards on account deletion. Otherwise a rebuild removes them, and the note goes in the spec.

**16 (low). Many sequential Valkey calls.** `service.py:241`; `api/v1/segments.py:33`; `valkey.py:23`.
- What happens: up to 300 calls per request, which share the connection pool with the rate limiter. Under load, uploads can fail closed.
- Fix: group the updates per key, or send them in one pipeline.

**18 (low). Fallback reads scan all partitions.** `api/v1/leaderboards.py:52-61`.
- Fix: read the totals table for team and building boards, after 22 is fixed.

**23 (low). Rebuild runs three scans.** `leaderboards.py:146-149`.
- Fix: one `GROUPING SETS` scan (31 ms against 66 ms measured).

### Database speed and locks

**8 (medium). Deleting a user is slow.** `0004_segments.py:87-89, 138-144, 159-161`.
- What happens: three foreign-key columns have no index. Measured: 4.8 s for a heavy user, 23 ms with indexes (insert overhead not measured).
- Fix (today, new migration):
  - `CREATE INDEX ix_climb_segment_checkin_id ON climb_segment (checkin_id);`
  - `CREATE INDEX ix_segment_receipt_user_id ON segment_receipt (user_id);`
  - `CREATE INDEX ix_fraud_flag_user_id ON fraud_flag (user_id);`

**9 (medium). Batches hold the user lock for about a second.** `service.py:173, 206, 266`; `db/session.py:32`.
- What happens: about 610 round trips per batch (776-1702 ms measured). Twenty concurrent batches from one user could fill the 20-connection pool (plausible, not measured).
- Fix: check receipts with one `= ANY` query, read the window in one range query, cache check-in context per check-in, and set `SET LOCAL lock_timeout`.

**20 (low). A check-in can't be purged alone.** `0004_segments.py:87-89`. Fix: drop old partitions before purging check-ins.

**24 (low). Unused index.** `0004_segments.py:122`. Fix: recheck with several seasons before dropping it.

**25 (low). Test assumes cold data.** `tests/segments/test_claim.py:663-665`. Fix: loosen the no-sequential-scan check.

### Requests, abuse and checks

**10 (medium). No body size limit; errors come before auth.** `infra/caddy/Caddyfile`; `api/v1/segments.py:4-5`.
- What happens: the body is read before auth. Malformed JSON gets 422 with no auth, which contradicts the docstring.
- Fix: `request_body { max_size ... }` in Caddy, and correct the docstring.

**14 (low). Users can fill the database with rejected rows.** `auth/ratelimit.py:34-35`.
- What happens: about 12,000 items an hour, each able to leave a receipt and a flag. Partition drops don't clear them.
- Fix: cap rejections per user; purge in the retention job.

**21 (low). Roles check has gaps.** `infra/sql/check_roles.sh:40, 106`. Fix: add a TRUNCATE probe, and stop treating "does not exist" as denied.

**22 (low). Contract describes a read path that doesn't exist.** `contracts/openapi.yaml:296`. Fix: correct the contract wording, and define what happens to totals on deletion.

## Possible spec changes (from the review)

- An aged-out owner stays until the next upload to that building. Standings can show a 0-point owner above a team with points.
- Spec section 5 says "another user's receipt" is only enforced for the same device id.

## Checked and correct (no action)

Lock order (no A/B vs B/A deadlock), tie rule, 7-day window, points formula at 299/300/301 steps, `game_event` in the same transaction, rollback behaviour, December/January partitions, NaN and huge numbers rejected per item, check-in and device spoofing blocked, no raw streams or coordinates stored, no SQL built from input, `floorwars_app` grants, user-delete cascades.
