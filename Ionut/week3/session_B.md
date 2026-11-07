# Session B: rules, upload endpoint, rate limits

**Name** `w3-b` | **Model** Opus 5.5 | **Effort** medium | **Branch** `feat/w3-segments-api` | **Ports** db 55502, valkey 56502 | **Peers** `w3-a` (repository and claim), `w3-c` (leaderboards helpers), `w3-lead`

Skills to load first: `token-saver`, `backend-conventions`, `scoring-rules`, `web-backend`.

Read: `Ionut/week3/spec.md` (all), `contracts/openapi.yaml` path `/segments` and schemas `SegmentBatch`, `Segment`, `SegmentFields`, `SegmentBatchResult`, `AcceptedSegment`, `RejectedSegment`, `BuildingFlip`, `Problem`, `server/app/api/deps.py`, `problems.py`, `server/app/api/v1/auth.py` and `checkins.py` (patterns), `server/app/auth/ratelimit.py` (the `Limiter`), `server/tests/conftest.py`, `helpers.py`.

## Part 1: start now, no database needed

1. `app/segments/schemas.py`: the request models. They must **accept** out-of-range numbers (finite or not) so a bad item is rejected per item and never fails the batch: strict types (`id`, `checkin_id` as UUIDs, `started_at` aware datetime, numbers as float or int, `steps` integer), `extra="forbid"`, 1 to 100 items, the batch has a required top-level `device_id` (contract 0.5.0-draft); an item has exactly the contract's `Segment` fields and no device field.
2. `app/segments/rules.py`: constants (spec section 3) and `check_item` (spec section 4), **pure functions**, with `ItemContext` from `w3-a`'s `models.py` (use a local stand-in until `INTERFACES READY` arrives). Boundary tests on both sides of every bound and the rule order. `points_for` lives in `w3-a`'s `claim.py`: import it once it exists.
3. The route `POST /v1/segments`, the `Limiter` bucket (60 per hour, fail closed), header validation, problem types, the response model, registered in `_FEATURE_ROUTERS`. The service calls the repository through the interface of spec section 6.

## Part 2: after `w3-a` reports `A1 READY` and its PR is merged (merge `origin/main` into your branch)

4. `app/segments/service.py` (spec section 5): the transaction, receipts, per-item results, flips, post-commit leaderboard calls through a `Protocol` with a no-op default (`w3-c` provides `app/leaderboards.py`; use it once merged).
5. Tests (spec section 10): idempotency (including a rejected duplicate), partial success, the late-ending climb, rate limits, 401, 422 shapes, no leak between users, the response matches the contract (extend `tests/auth/test_contract.py`-style checks if present: paths, methods, status codes for `/v1/segments`).
6. Push, open the PR, tell `w3-lead`: `B READY <PR number>`.

## Verify (from `server/`, own containers `fw-w3-b-db` 55502, `fw-w3-b-valkey` 56502)

`ruff check .`, `ruff format --check .`, `mypy app`, `pytest -q`, `alembic check`. Summary lines only.

## Report (short)
Branch, commits, verify lines, decisions beyond the spec, open questions.
