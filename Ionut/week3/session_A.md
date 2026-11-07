# Session A: schema, claim transaction, scoring (hardest, critical path)

**Name** `w3-a` | **Model** Opus 5.5 | **Effort** high | **Branches** `feat/w3-schema` (A1), then `feat/w3-claim` (A2) | **Ports** db 55501, valkey 56501 | **Peers** `w3-b` (needs your interfaces), `w3-c`, `w3-lead`

Skills to load first: `token-saver`, `backend-conventions`, `scoring-rules`, `web-backend` (skip a skill that is not found).

Read: `Ionut/week3/spec.md` (all), `server/app/db/models.py`, `server/migrations/versions/0003_checkin.py` and `0002_auth.py` (patterns), `server/app/checkins/repository.py` (locking pattern), `server/tests/conftest.py` and `helpers.py`, `server/docs/er_review.md` items 2 to 5. Nothing else unless a step names it.

## A1: schema and repository (do this FIRST, open the PR early: it unblocks B, C and D)

1. `server/app/segments/models.py`: the frozen dataclasses of spec section 6, with the signatures of `repository.py` as functions that raise `NotImplementedError` where not yet built, so `w3-b` can import them at once. Commit, then message `w3-b` and `w3-c`: `INTERFACES READY <sha>`.
2. Migration `0004_segments` exactly as spec section 2, SQLAlchemy models appended to `app/db/models.py` (partitioned table via `postgresql_partition_by`), `app/segments/partitions.py` and its CLI. `alembic upgrade head`, `alembic check` (clean; if autogenerate cannot compare the partitioned table, add an `include_object` rule in `migrations/env.py` and explain it in a comment), `downgrade -1` then `upgrade head`.
3. `repository.py` implementations (spec section 6, except `recompute_owner`), including `device_belongs`. Use bound parameters only. `load_context` is one query where possible.
4. Tests: `test_schema.py` and `test_partitions.py` (spec section 10). Run `infra/sql/check_roles.sh` (see its header for the container variables) to prove the app role can use the new tables and the migrator creates them.
5. Push `feat/w3-schema`, open the PR, tell `w3-lead`: `A1 READY <PR number>`.

## A2: claim transaction (after A1, on a new branch from your A1 work)

1. `app/segments/claim.py`: `rolling_points`, `recompute_owner`, `points_for(steps, prior_steps)` (the formula of spec section 3; pure and tested alone). Ownership SQL uses the window function approach for "who reached the tied total first". Insert the `game_event` row (`kind='building_flipped'`) inside `recompute_owner` and return the `Flip` with its `event_id`.
2. Concurrency tests (spec section 10): real threads with separate sessions against the test database. They must fail if the lock on `building_claim` or the user-row lock is removed (try removing it once to prove the test bites, then restore it).
3. `EXPLAIN` of the owner query: record the plan line in the PR description.
4. Push `feat/w3-claim`, PR, tell `w3-lead` `A2 READY <PR number>`.

## Verify (from `server/`, own containers `fw-w3-a-db` 55501 and `fw-w3-a-valkey` 56501; set `FLOORWARS_ENV=dev` and the three test URLs)

`ruff check .`, `ruff format --check .`, `mypy app` (strict), `pytest -q` (the whole suite), `alembic upgrade head`, `alembic check`, `alembic downgrade -1` then `upgrade head`. Paste only the summary lines. Stop your containers when done.

## Report (short)
Branch, commits, verify lines, the `EXPLAIN` line, decisions beyond the spec, open questions. Do not paste file contents.
