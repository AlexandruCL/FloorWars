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

Indexes on `climb_segment` (created on the parent): `(building_id, started_at DESC) WHERE status = 'verified'`, `(user_id, started_at DESC)`, `(season_id, team_id)` for season totals. Foreign keys, ownership of existing objects and grants: the migrator creates the tables, so `ALTER DEFAULT PRIVILEGES` from `infra/sql/roles.sql` already gives `floorwars_app` its DML rights; verify with `infra/sql/check_roles.sh` (session A).

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
| `STEPS_PER_M_MIN`, `STEPS_PER_M_MAX` | 4.0, 8.0 |
| `CADENCE_MAX_STEPS_PER_S` | 3.0 (not in the plan; tunable) |
| `VERIFIED_STEPS_PER_10_MIN` | 600 |
| `UPLOADS_PER_HOUR` | 60 (requests, Valkey bucket, existing `Limiter`) |
| `FULL_POINT_STEPS_PER_HOUR` | 300 (1.0 point per step up to here), then `REDUCED_POINT_PER_STEP` 0.5 |
| `OWNERSHIP_WINDOW` | 7 days |

**Points** for a verified segment with `s` steps and `h` verified steps of the same user in the 60 minutes before its `started_at` (earlier items of the same batch included): `full = max(0, min(s, 300 - h))`, `points = floor(full * 1.0 + (s - full) * 0.5)`. `steps_scored = s` for verified, 0 for rejected.

## 4. Rules and reasons (pure function `rules.check_item(item, ctx)`; fixed order, first failure wins)

1. `started_at_range`: `started_at` older than 7 days or more than 5 minutes in the future.
2. `steps_range`: `steps` outside 1..2000. `ascent_range`: `ascent_m` outside 2.0..120.0. `duration`: `duration_s` outside 5..180 (NaN or infinity count as outside). `stair_prob_range`: `stair_prob` outside 0..1 or not finite (added after `duration`, same fraud flag as the other range rules). `classifier_version` longer than 64 characters or with control characters is a 422 for the batch (contract `maxLength`/`pattern`).
3. `no_checkin`: `checkin_id` unknown, belongs to another user, or `started_at` not inside its `valid_during`. `building_mismatch`: `building_id` differs from the check-in's building.
4. `season_inactive`: no season contains `started_at`. `no_team`: the user has no membership in that season.
5. `speed`: `vert_speed_mps` outside 0.1..0.9, or inconsistent with `ascent_m / duration_s` by more than 20 percent.
6. `pressure_steps_mismatch`: `steps / ascent_m` outside 4.0..8.0.
7. `cadence`: `steps / duration_s` above 3.0.
8. `rate_limit`: verified steps of the user in `(started_at - 10 min, started_at]` plus this segment's steps above 600.

Rules 1 to 2 and 5 to 7 are pure (no database). Rules 3, 4 and 8 need `ctx` (loaded by the repository). `fraud_flag` rows are written for every rejection **except** `started_at_range`, `no_checkin`, `season_inactive`, `no_team` (state problems, not cheating). Stored rejected rows need valid `team_id`, `season_id`, `building_id`, `checkin_id`; when rules 1 to 4 fail the item is answered as rejected and recorded only in `segment_receipt` (no `climb_segment` row).

## 5. Batch algorithm (`app/segments/service.py`, owned by B)

1. Request level (before any database work): `Limiter` bucket `fw:rl:seg:user:{user_id}` 60 per hour (429 `Retry-After`, fail closed 503 if Valkey is down); batch of 1..100 items (422 otherwise); header `Idempotency-Key` required (non-empty, at most 255 characters). The key is logged (not secret) and otherwise informational: duplicates are decided per segment by `segment_receipt`.
2. One transaction: `repository.lock_user(db, user_id)` (`SELECT ... FROM "user" WHERE id = :id FOR UPDATE`), then `repository.device_belongs(db, user_id, batch.device_id)` (403 `device-unknown` and roll back if not), then items in ascending `started_at`:
   - `receipt = repository.get_receipt(db, device_id, id)`; if present: answer from it (verified: accepted without `points`; rejected: rejected with the stored reason). No other effect.
   - Otherwise run `rules.check_item`. `repository.insert_receipt(...)` for every new item. For a verified item: `insert_segment`, `add_score`, remember `(season_id, building_id)` as affected; for a rejected item with a stored row: `insert_segment` (status rejected) and `add_fraud_flag` when the reason qualifies.
3. After all items: for each affected `(season_id, building_id)` in **ascending order**: `claim.recompute_owner(db, season_id, building_id, now)`; each returns a `Flip` or `None` (and has already inserted the `game_event` row).
4. Commit. **After** the commit, best effort (never fail the request): `leaderboards.record_verified(...)` per verified segment and `leaderboards.publish_flip(...)` per flip. A Valkey error is logged and ignored (leaderboards are rebuildable from the database).
5. Response 200 `SegmentBatchResult {accepted:[{id, steps_scored, points?}], rejected:[{id, reason}], flips:[{building_id, from_team, to_team, at}]}` (team codes in `from_team`/`to_team`, as the contract says).

## 6. Repository interface (owned by A, `app/segments/repository.py`; sync SQLAlchemy `Session`)

```python
lock_user(db, user_id) -> bool                       # False if the user row is gone (then 401)
device_belongs(db, user_id, device_id) -> bool       # False -> 403 device-unknown
get_receipt(db, device_id, segment_id) -> Receipt | None
insert_receipt(db, device_id, segment_id, user_id, status, reject_reason, steps_scored) -> None
load_context(db, user_id, checkin_id, started_at) -> ItemContext   # checkin (building, valid_during, owner),
                                                                    # season_id | None, team_id | None
verified_steps_between(db, user_id, start, end) -> int
insert_segment(db, row: SegmentRow) -> None
add_fraud_flag(db, segment_id, started_at, user_id, rule) -> None
add_score(db, season_id, building_id, team_id, points, steps) -> None
# app/segments/claim.py
recompute_owner(db, season_id, building_id, now) -> Flip | None   # ensures the claim row, locks it, applies
                                                                   # the 7-day rule and the tie rule, writes game_event
rolling_points(db, season_id, building_id, now) -> list[TeamPoints]   # same query, used by standings
```

`Receipt`, `ItemContext`, `SegmentRow`, `Flip`, `TeamPoints` are frozen dataclasses in `app/segments/models.py` (A writes them in its first commit). `Flip` has `building_id`, `season_id`, `from_team_id`, `to_team_id`, `from_code`, `to_code`, `at`, `event_id`.

## 7. Valkey (owned by C, `app/leaderboards.py`)

- Keys: `fw:lb:s{season}:users` (member user id), `fw:lb:s{season}:teams` (member team id), `fw:lb:s{season}:b{building}:teams` (member team id); score = season points. `PUBLISH` channel `fw:events`, message JSON `{"type":"building_flipped","event_id":N,"building_id":..,"from_team":"AC","to_team":"ETC","at":"..."}`.
- `record_verified(vk, season_id, user_id, team_id, building_id, points)`, `publish_flip(vk, flip)`, `rebuild(db, vk, season_id)` (from `climb_segment`, season totals, idempotent), `top(...)`. B calls the first two behind a small `Protocol`, with a no-op default when Valkey is not configured.
- Reads fall back to a database aggregate when Valkey is down or a key is missing (then rebuild once).

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
