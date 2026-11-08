# Week 3 shared spec (Ionut): segments, claims, scoring, standings

Binding for every Week 3 session. Source: `IMPLEMENTATION_PLAN.md` sections 2, 3.1, 3.3, 3.4, 5, 7.7 and the decisions below. If this file and the plan disagree, this file wins for Week 3 and session E fixes the plan. Names written in `code` are fixed: change one only after asking the lead session (`w3-lead`).

## 1. Decisions (Ionut, 2026-11-07)

1. **Idempotency:** a separate unpartitioned table `segment_receipt` with `PRIMARY KEY (device_id, id)`, inserted `ON CONFLICT DO NOTHING` inside the batch transaction.
2. **Ownership:** a building's owner is recomputed inside the claim transaction from verified segments of the **rolling 7 days** (by `started_at`). `team_building_score` keeps **season totals** (standings history, leaderboards).
3. **Ties:** the current owner keeps the building. A flip needs strictly more points. If nobody owns it yet, or the owner is not among the tied top teams, the team that **reached** the tied total first wins.
4. Rejected segments are **stored** (status `rejected` with `reject_reason`), so the app's history can show the reason. Out-of-bounds numbers are therefore accepted by the request model and rejected per item (contract 0.4.x: 422 is only for a body that is not a valid batch).
5. Contract **0.5.0-draft** (done by the lead before the sessions start) adds three rejection reasons (`started_at_range`, `season_inactive`, `no_team`) and a required batch-level `device_id` (uuid) on `SegmentBatch`, because neither the token nor the segment carries the device. The server checks it belongs to the signed-in user (`device` primary key `(user_id, id)`): otherwise 403 `device-unknown` for the whole request.

## 2. Data model: migration `0004_segments` (down_revision `0003_checkin`, expand-only)

| Table | Columns and constraints |
|---|---|
| `climb_segment` (**partitioned** `BY RANGE (started_at)`, monthly) | `id uuid`, `device_id uuid`, `user_id uuid NOT NULL FK "user" ON DELETE CASCADE`, `team_id int NOT NULL FK team`, `season_id int NOT NULL FK season`, `checkin_id uuid NOT NULL` (FK `checkin(id)`), `building_id int NOT NULL FK building`, `status text NOT NULL CHECK (status IN ('verified','rejected'))`, `reject_reason text NULL`, `steps int NOT NULL`, `steps_scored smallint NOT NULL CHECK (steps_scored BETWEEN 0 AND 2000)`, `points int NOT NULL CHECK (points >= 0)`, `ascent_m real NOT NULL`, `duration_s real NOT NULL`, `vert_speed_mps real NOT NULL`, `stair_prob real NOT NULL`, `classifier_version text NOT NULL`, `started_at timestamptz NOT NULL`, `received_at timestamptz NOT NULL DEFAULT now()`. **PK `(id, started_at)`.** CHECK: `status = 'rejected' OR (steps BETWEEN 1 AND 2000 AND ascent_m BETWEEN 2.0 AND 120.0 AND stair_prob BETWEEN 0 AND 1)`; CHECK `(status = 'rejected') = (reject_reason IS NOT NULL)`. Rejected rows with unusable `team_id`/`season_id`/`building_id` are not stored (see rule order, section 4). |
| `segment_receipt` | `device_id uuid`, `id uuid`, `user_id uuid NOT NULL FK ... ON DELETE CASCADE`, `status text NOT NULL`, `reject_reason text NULL`, `steps_scored smallint NOT NULL DEFAULT 0`, `created_at timestamptz NOT NULL DEFAULT now()`, **PK `(device_id, id)`**. |
| `fraud_flag` | `id bigint GENERATED ALWAYS AS IDENTITY PK`, `segment_id uuid NOT NULL`, `segment_started_at timestamptz NOT NULL`, `user_id uuid NOT NULL FK ... ON DELETE CASCADE`, `rule text NOT NULL`, `created_at timestamptz NOT NULL DEFAULT now()`, `resolved_at timestamptz NULL`. **No FK to `climb_segment`** (a partition drop must not be blocked). Index `(created_at) WHERE resolved_at IS NULL`. |
| `team_building_score` | `season_id`, `building_id`, `team_id` (composite PK, FKs), `points int NOT NULL DEFAULT 0 CHECK (points >= 0)`, `steps int NOT NULL DEFAULT 0`. Season totals. |
| `building_claim` | `season_id`, `building_id` (composite PK, FKs), `team_id int NULL FK team` (null = unowned), `claimed_at timestamptz NULL`. The row is created (`INSERT ... ON CONFLICT DO NOTHING`) before it is locked, so the first two climbs in a building cannot race. |
| `game_event` | `id bigint GENERATED ALWAYS AS IDENTITY PK`, `kind text NOT NULL CHECK (kind IN ('building_flipped','season_state'))`, `season_id int NULL`, `building_id int NULL`, `from_team int NULL`, `to_team int NULL`, `payload jsonb NOT NULL DEFAULT '{}'`, `created_at timestamptz NOT NULL DEFAULT now()`. Index `(created_at)`. Written inside the claim transaction (plan 7.2.1). |

Indexes on `climb_segment` (created on the parent): `(building_id, started_at DESC) WHERE status = 'verified'`, `(user_id, started_at DESC)`, `(season_id, team_id)` for season totals. Migration `0005_fk_indexes` adds indexes on the foreign keys scanned when a user is deleted: `climb_segment(checkin_id)`, `segment_receipt(user_id)`, `fraud_flag(user_id)`. Foreign keys, ownership of existing objects and grants: the migrator creates the tables, so `ALTER DEFAULT PRIVILEGES` from `infra/sql/roles.sql` already gives `floorwars_app` its DML rights; verify with `infra/sql/check_roles.sh` (session A).

**Partitions:** `app/segments/partitions.py` has `ensure_partitions(conn, months_ahead=2, now=None)` (idempotent, `CREATE TABLE IF NOT EXISTS climb_segment_YYYYMM PARTITION OF ...`). The migration creates the current month and the next two. A CLI `python -m app.segments.partitions` runs it (needs the migrator role). Scheduling is Week 5 (Celery beat): leave a TODO in the README. No default partition: a `started_at` outside the partitioned range is rejected as `started_at_range` before the insert.

## 3. Constants (module `app/segments/rules.py`, named, one place; later moved to the `config` table)

| Name | Value |
|---|---|
| `BATCH_MAX` | 100 (contract) |
| `STARTED_AT_MAX_AGE` | 7 days; `STARTED_AT_FUTURE_SKEW` 5 minutes |
| `ASCENT_MIN_M`, `ASCENT_MAX_M` | 2.0, 120.0 |
| `STEPS_MIN`, `STEPS_MAX` | 1, 2000 |
| `DURATION_MIN_S`, `DURATION_MAX_S` | 5.0, 180.0 |
| `SPEED_MIN_MPS`, `SPEED_MAX_MPS` | 0.1, 0.9 |
| `STEPS_PER_M_MIN`, `STEPS_PER_M_MAX` | 4.0, 10.0 |
| `CADENCE_MAX_STEPS_PER_S` | 3.0 (not in the plan; tunable) |
| `VERIFIED_STEPS_PER_10_MIN` | 600 |
| `OVERLAP_TOLERANCE` | 1 ms |
| `UPLOADS_PER_HOUR` | 60 (requests, Valkey bucket, existing `Limiter`) |
| `REJECTED_STORED_PER_HOUR` | 200 (rejected items stored per user and hour, Valkey bucket `seg:rej`, `RateLimiter.hit`) |
| `FULL_POINT_STEPS_PER_HOUR` | 300 (1.0 point per step up to here), then `REDUCED_POINT_PER_STEP` 0.5 |
| `OWNERSHIP_WINDOW` | 7 days |

**Points** for a verified segment with `s` steps and `h` = the user's verified steps with `started_at` in the same UTC clock hour as this segment's (earlier items of the same batch included; a fixed hour makes a verified segment's points independent of upload order, apart from rounding per climb; whether it passes rule 9 still depends on order): `full = max(0, min(s, 300 - h))`, `points = floor(full * 1.0 + (s - full) * 0.5)`. `steps_scored = s` for verified, 0 for rejected.

## 4. Rules and reasons (pure functions; fixed order, first failure wins)

`rules.check_item` runs all of them. The service runs the same parts with its queries in between: `check_bounds` (1, 2), `check_state_and_physics` (3 to 7), `check_limits` (8, 9).

1. `started_at_range`: `started_at` older than 7 days or more than 5 minutes in the future.
2. `steps_range`: `steps` outside 1..2000. `ascent_range`: `ascent_m` outside 2.0..120.0. `duration`: `duration_s` outside 5..180 (NaN or infinity count as outside). `stair_prob_range`: `stair_prob` outside 0..1 or not finite (added after `duration`, same fraud flag as the other range rules). A `stair_prob` in range but too small for `real` (below 1e-37) passes and is stored as 0. `classifier_version` longer than 64 characters or with control characters is a 422 for the batch (contract `maxLength`/`pattern`).
3. `no_checkin`: `checkin_id` unknown, belongs to another user, or `started_at` not inside its `valid_during`. `building_mismatch`: `building_id` differs from the check-in's building.
4. `season_inactive`: no season contains `started_at`. `no_team`: the user has no membership in that season.
5. `speed`: `vert_speed_mps` outside 0.1..0.9, or inconsistent with `ascent_m / duration_s` by more than 20 percent.
6. `pressure_steps_mismatch`: `steps / ascent_m` outside 4.0..8.0.
7. `cadence`: `steps / duration_s` above 3.0.
8. `overlap`: `[started_at, started_at + duration_s)` overlaps that of a verified segment of the same user. Climbs that only touch at an end do not overlap (1 ms tolerance for `real` rounding).
9. `rate_limit`: verified steps of the user with `started_at` in `(started_at - 10 min, started_at + 10 min)`, plus this segment's steps, above 600. Both sides are counted, so upload order cannot bypass the cap.

Rules 1 to 2 and 5 to 7 are pure (no database). Rules 3, 4, 8 and 9 need `ctx` (loaded by the repository). `fraud_flag` rows are written for every rejection **except** `started_at_range`, `no_checkin`, `season_inactive`, `no_team` (state problems, not cheating). Stored rejected rows need valid `team_id`, `season_id`, `building_id`, `checkin_id`; when rules 1 to 4 fail the item is answered as rejected and recorded only in `segment_receipt` (no `climb_segment` row). `overlap` and `rate_limit` store a rejected row, and are flagged only when the honest explanation is ruled out: `rate_limit` when verified steps in `(started_at - 10 min, started_at)` plus this segment's are above 600 (not when only later climbs fill the cap), `overlap` when the overlapping verified segment came from the same device (not a second phone). Only verified segments count for rules 8 and 9, so a rejected row blocks nothing.

## 5. Batch algorithm (`app/segments/service.py`, owned by B)

1. Request level (before any database work): `Limiter` bucket `fw:rl:seg:user:{user_id}` 60 per hour (429 `Retry-After`, fail closed 503 if Valkey is down); batch of 1..100 items (422 otherwise); header `Idempotency-Key` required (non-empty, at most 255 characters). The key is logged (not secret) and otherwise informational: duplicates are decided per segment by `segment_receipt`. Stored-rejection cap: each rejected item that would be stored takes one token of the per-user hourly bucket `seg:rej` (`REJECTED_STORED_PER_HOUR`). Past the cap the item is answered with its real reason but no `segment_receipt`, `fraud_flag` or `climb_segment` row is written (a resend is judged again); a Valkey error mid-batch counts as capped; verified items never use the bucket; no 429, no new reason. `repository.purge_rejected(db, now)` (called by the Week 5 retention job, not scheduled yet) deletes rejected receipts and resolved flags older than 30 days and unresolved flags older than 365 days.
2. One transaction: `repository.lock_user(db, user_id)` (`SELECT ... FROM "user" WHERE id = :id FOR UPDATE` under a 5 s `lock_timeout`, restored afterwards so later lock waits are not limited; a longer wait answers 503 with `Retry-After` and stores nothing), then `repository.device_belongs(db, user_id, batch.device_id)` (403 `device-unknown` and roll back if not), then items in ascending `(started_at, id)` (the reads below are done once per batch since finding 9, section 5a; the answers are the same):
   - `receipt = repository.get_receipt(db, device_id, id)`; if present: answer from it (verified: accepted without `points`; rejected: rejected with the stored reason; a receipt of another user: rejected `no_checkin`). No other effect.
   - Otherwise, before the rules, `repository.segment_exists(db, id, started_at)` (any user, any status): a resend from a second device, or an id another user stored, is not a new climb. It is answered rejected `no_checkin` with a receipt, and no segment row, score or flag.
   - Otherwise check in this order, first failure wins: bounds (rules 1, 2), state (3, 4), physics (5 to 7), `overlap` (8), `rate_limit` (9). The queries for rules 8 and 9 run only for an item that passed rules 1 to 7. `repository.insert_receipt(...)` for every new item. For a verified item: `insert_segment`, remember `(season_id, building_id, team_id)` and its points as affected; for a rejected item with a stored row: `insert_segment` (status rejected); `add_fraud_flag` follows section 4 (every reason except `started_at_range`, `no_checkin`, `season_inactive`, `no_team`, and the honest cases of `overlap` and `rate_limit`) and is written even when the item has no `climb_segment` row (for example a range rule or `building_mismatch`). An insert that loses to a concurrent upload of the same `(id, started_at)` is answered rejected `no_checkin`, with no score and no flag.
   - After the item loop, `add_score` runs once per `(season, building, team)` in ascending order, before `recompute_owner` (totals are the same as per item; one ordered pass avoids a deadlock between teammates' batches).
3. After all items: for each affected `(season_id, building_id)` in **ascending order**: `claim.recompute_owner(db, season_id, building_id, now)`; each returns a `Flip` or `None` (and has already inserted the `game_event` row).
4. Commit. **After** the commit, best effort (never fail the request): `leaderboards.record_verified(...)` per verified segment and `leaderboards.publish_flip(...)` per flip. A Valkey error is logged and ignored (leaderboards are rebuildable from the database).
5. Response 200 `SegmentBatchResult {accepted:[{id, steps_scored, points?}], rejected:[{id, reason}], flips:[{building_id, from_team, to_team, at}]}` (team codes in `from_team`/`to_team`, as the contract says).

### 5a. Batch cost (review finding 9; 2026-11-08)

The user lock is held for the whole batch, so the batch must not cost one set of queries per item. Target for a 100-item batch: at most about 10 reads for the whole batch plus the writes (one `insert_segment` per stored row, one `add_fraud_flag` per flag), one multi-row receipt insert, and the claim step. Results stay identical (statuses, reasons, points, flips, flags, receipts, rows).

Reads that may be done once per batch, after `lock_user` and `device_belongs`, and then kept in memory:

- **Receipts** of the device for all item ids (`id = ANY`). The batch adds its own answers to the map as it goes (first answer wins, like `ON CONFLICT DO NOTHING`), so a repeated id in one batch is answered as before. The receipts are written once, in one multi-row insert after the item loop (`created_at` is the transaction time either way).
- **Stored segments** `(id, started_at)` for the items without a receipt (any user). Rows the batch inserts need no entry: each comes with a receipt, which answers a repeat first.
- **Contexts** of the items that pass rules 1 and 2: one query, the joins of `load_context` over an `unnest` of `(checkin_id, started_at)`, so each item gets the same check-in, season and team as before. Rules 3 to 7 then run for all items before the loop.
- **The user's verified climbs** (`started_at`, stored end, `steps_scored`, `device_id`) in the time ranges the items can read: for each item that passes rules 1 to 7, from `min(started_at - 10 min, started_at - DURATION_MAX_S, its clock hour)` to `max(started_at + 10 min, its end, its clock hour + 1 h)` (the duration terms only guard a later change of the constants), merged into a few ranges; no query when no item passes rules 1 to 7. Every step count and overlap test of sections 4 and 5 is answered from this list with the same bounds as the SQL. An accepted item is appended with the end the database stored (`insert_segment` returns it), because `duration_s` is a `real`.

Why this is safe: only the user's own batches write the user's verified rows, check-ins and receipts, and they are serialised by the user lock. Not under the user lock, so read once at the start instead of per item (races with no fixed order; the window is now the batch instead of one item):

- Another user committing the same `(id, started_at)` during the batch. An item that stores a row still loses on the `ON CONFLICT` of `insert_segment` and is answered `no_checkin`. An item rejected by a receipt-only rule that is flagged (`steps_range`, `ascent_range`, `duration`, `stair_prob_range`, `building_mismatch`), or past the rejection cap, keeps its real reason and gets its flag where the per-item check might have answered `no_checkin`. No points are lost or doubled. Accepted (Ionut, 2026-11-08, finding 9).
- A team join during the batch: the batch sees the team state of its start; before, items after the join could see the new team.

## 6. Repository interface (owned by A, `app/segments/repository.py`; sync SQLAlchemy `Session`)

```python
lock_user(db, user_id) -> bool                       # False if the user row is gone (then 401)
device_belongs(db, user_id, device_id) -> bool       # False -> 403 device-unknown
# Used by the batch since finding 9 (one query each, section 5a):
get_receipts(db, device_id, segment_ids) -> dict[UUID, Receipt]
insert_receipts(db, receipts: Sequence[Receipt]) -> None   # one multi-row insert, ON CONFLICT DO NOTHING
stored_segments(db, keys: {(id, started_at)}) -> set     # the stored keys, any user, any status
load_contexts(db, user_id, [(checkin_id, started_at)]) -> list[ItemContext]   # in the order given
verified_climbs(db, user_id, ranges) -> list[VerifiedClimb]   # started_at in any closed range; with the stored end
# Per-item forms, kept for tests and the reference path in tests/segments/test_batch_equivalence.py:
get_receipt(db, device_id, segment_id) -> Receipt | None
insert_receipt(db, device_id, segment_id, user_id, status, reject_reason, steps_scored) -> None
load_context(db, user_id, checkin_id, started_at) -> ItemContext   # checkin (building, valid_during, owner),
                                                                    # season_id | None, team_id | None
verified_steps_around(db, user_id, at, window) -> int   # started_at in (at - window, at + window)
verified_steps_before(db, user_id, at, window) -> int   # started_at in (at - window, at)
verified_steps_in_hour(db, user_id, at) -> int          # started_at in the UTC clock hour of at
overlaps_verified(db, user_id, started_at, duration_s, *, device_id=None) -> bool
segment_exists(db, id, started_at) -> bool           # any user, any status
insert_segment(db, row: SegmentRow) -> datetime | None   # the stored end; None if (id, started_at) exists
add_fraud_flag(db, segment_id, started_at, user_id, rule) -> None
add_score(db, season_id, building_id, team_id, points, steps) -> None
# app/segments/claim.py
recompute_owner(db, season_id, building_id, now) -> Flip | None   # ensures the claim row, locks it, applies
                                                                   # the 7-day rule and the tie rule, writes game_event
rolling_points(db, season_id, building_id, now) -> list[TeamPoints]   # same query, used by standings
```

`Receipt`, `ItemContext`, `VerifiedClimb`, `SegmentRow`, `Flip`, `TeamPoints` are frozen dataclasses in `app/segments/models.py` (A writes them in its first commit). `Flip` has `building_id`, `season_id`, `from_team_id`, `to_team_id`, `from_code`, `to_code`, `at`, `event_id`.

## 7. Valkey (owned by C, `app/leaderboards.py`)

- Keys: `fw:lb:s{season}:users` (member user id), `fw:lb:s{season}:teams` (member team id), `fw:lb:s{season}:b{building}:teams` (member team id); score = season points. `PUBLISH` channel `fw:events`, message JSON `{"type":"building_flipped","event_id":N,"building_id":..,"from_team":"AC","to_team":"ETC","at":"..."}`.
- `record_verified(vk, season_id, user_id, team_id, building_id, points)`, `publish_flip(vk, flip)`, `rebuild(db, vk, season_id)` (from `climb_segment`, season totals, idempotent), `top(...)`. B calls the first two behind a small `Protocol`, with a no-op default when Valkey is not configured.
- Reads fall back to a database aggregate when Valkey is down. On a missing key: if the database holds points for that board, rebuild the season once and read again; without points the board is empty and nothing is rebuilt. (Superseded by the addendum below.)

### 7a. Addendum: board consistency (review findings 5, 6, 7, 11; 2026-11-08)

- **Built marker** `fw:lb:s{season}:built` (value `1`, expiry 1 h). `rebuild` sets it after writing every key; it means "the boards of this season equal the database". A missing marker means **needs rebuild**: after Valkey data loss, a failed update, or the hourly expiry (which bounds drift when Valkey was unreachable and the marker could not be deleted).
- **Reads**: marker missing, rebuild the season, then read. Marker present, a missing key is an empty board (no rebuild, no database query). A rebuild that cannot finish cleanly (lock taken, or an upload overlapped) leaves the marker missing and the read is answered from the database.
- **Rebuild lock** `fw:lb:s{season}:lock`: `SET NX PX 30000` with a random token around the rebuild. Released only by its owner (token compared in a Lua script); a rebuild that finds its lock gone or replaced deletes the marker. Temp keys are per rebuild (`{key}:rebuild:{token}`) and deleted if a board is not finished. The rebuild stops (and releases) after half the lock expiry, checked before each board and each 500-member chunk; a season that always needs longer never converges and its reads stay on the database. A rebuild that finds the marker already set after taking the lock only releases it (the marker is set with `NX`, so its expiry is not reset). The rebuild also deletes building keys that no longer have points.
- **Uploads** add a segment's points with one Lua script, atomic in Valkey: lock held, append `:dirty` to the lock value and skip (the rebuild then deletes the marker instead of setting it, so the next read rebuilds); no marker, skip (the rebuild will count the segment); otherwise the three `ZINCRBY`. The upload never waits: whether a running rebuild's snapshot includes a just-committed segment is unknown, so applying after a wait could double-count.
- **Failures**: any error while adding points is logged (`logger.exception`), the marker of every season in the batch is deleted (best effort, each on its own) and a running rebuild of that season is marked dirty (one Lua script), the upload still succeeds. Flips are published in their own `try`.
- **Deleted users**: there is no account-deletion path yet (`DELETE /me` is in the contract only). Deleting a user cascades to its `climb_segment` rows, so a rebuild drops the user and its points from every board. Without that rebuild the user stays on the boards for up to 1 h (the marker expiry), so the deletion path must delete the season markers when it is built.
- **Accepted risks** (Ionut, 2026-11-08):
  - (a) Option A, no code: a segment is counted twice if a whole rebuild lies between the upload's commit and its `EVAL`. The window runs from any commit before the rebuild's last query to any `EVAL` after its finish, plus the skew between the three separate board queries. It heals at the next rebuild, at the latest when the marker expires (1 h).
  - (b) The client retries a command once on a timeout (`app/valkey.py`). If the first `EVAL` ran but its reply was lost, the retry adds the points again and no `ValkeyError` is raised, so the marker stays. Same as the old `ZINCRBY`; healed by the 1 h expiry.
  - (c) Under steady uploads every rebuild can be invalidated (an upload during it marks it dirty), and reads go to the database. Bounded at pilot scale; a scheduled rebuild (Celery beat) is the later remedy.

## 8. Read endpoints (owned by C)

- `GET /v1/buildings` (bearer): `[{id, name}]` ordered by name.
- `GET /v1/buildings/{id}/standings` (bearer): 404 `building-not-found`; `season_id` of the active season (404 `no-active-season` otherwise); `owner` (`Team` or null), `claimed_at`, `window_start` (now minus 7 days), `teams` = every team with its **rolling 7-day** points (0 for none), ordered by points desc then code. Owner and points come from one query on `building_claim` and `rolling_points`.
- `GET /v1/leaderboards?scope=individual|team|building&season_id&building_id&limit` per the contract. Open point: for `scope=building` the contract requires `building_id`; implement it as "teams ranked in that building for the season" and tell the lead so the contract description says it.

## 9. File ownership (one owner per file; others ask the owner)

| Session | Owns |
|---|---|
| A | `server/migrations/versions/0004_segments.py`, `server/app/db/models.py` (append only), `server/app/segments/{models,repository,claim,partitions}.py`, `server/tests/segments/test_schema.py`, `test_claim.py`, `test_partitions.py` |
| B | `server/app/segments/{schemas,rules,service}.py`, `server/app/api/v1/segments.py`, `server/tests/segments/test_rules.py`, `test_api.py`, `test_idempotency.py`, `test_rate_limits.py` |
| C | `server/app/leaderboards.py`, `server/app/api/v1/{buildings,leaderboards}.py`, `server/tests/read/*` |
| D | `tools/fake_segments/*`, `tools/e2e/*`, `server/tests/replay/*` |
| E | `README.md`, `IMPLEMENTATION_PLAN.md`, `docs/*`, `server/README.md` |
| lead | `contracts/openapi.yaml`, `app/src/api/schema.ts`, `server/app/api/v1/__init__.py` merge conflicts, merges |

The line registering a router in `server/app/api/v1/__init__.py` (`_FEATURE_ROUTERS`) is the one expected merge conflict (B, C): resolve it by listing all routers.

## 10. Tests that must exist (names are guidance)

- A: schema (constraints, CHECKs, exclusion of bad rows), partitions created and idempotent, a row routed to the right partition, `recompute_owner` (first owner, flip, tie keeps owner, tie with no owner goes to the earliest, window ageing), **concurrency**: two threads each uploading climbs of different teams into the same building leave a consistent claim and one correct final owner; different buildings do not block each other; `EXPLAIN` of the owner query uses the partial index.
- B: every rule and its boundary values (both sides of each bound), rule order, points formula (0, 299, 300, 301 steps with and without earlier steps), batch partial success, duplicate resend returns the stored answer, a rejected duplicate returns the same reason, 600-steps rate limit, 60-uploads bucket (429, 503 when Valkey is down), 401, 422 (not a batch, 0 or 101 items, missing key), a climb that started inside the check-in but ends after `valid_until` still counts, the response carries no data from other users.
- C: standings (owner, zero-point teams listed, window), buildings list, each leaderboard scope, Valkey down falls back to the database, rebuild equals incremental.
- D: the replay harness (section in `session_D.md`) and the e2e script.

## 11. Rules for every session

Load the skill `token-saver` first. Read only this file, your own session file and the files they name. Targeted search before reading; for files over 300 lines read ranges only; never print full logs or test output (use `-q`, `tail`, `grep`). No new dependency without Ionut's approval. One commit per step, no Co-Authored-By or other trailer. Push your branch and open a PR into `main` when your checks pass; do not merge it yourself (the lead merges after CI is green). No VM access, no Azure, no secrets in output. Own Docker containers with the ports given in your session file. Python: `C:/Users/Ionut/Desktop/sem1_an4/msa/FloorWars/.venv/Scripts/python.exe`, written literally. Rename your worktree branch before pushing: `git branch -m feat/<name>`.

## 12. Known risks (accepted, 2026-11-07)

- A `started_at` outside the existing partitions (previous month through two ahead) is not checked per item: the insert would fail and the batch answers 500. Rule 1 (7 days back, 5 minutes ahead) cannot reach it while partitions are kept current; scheduling is Week 5 (Celery beat). Until then run the partition CLI after each migration and at the start of each month (runbook note by `w3-e`).
