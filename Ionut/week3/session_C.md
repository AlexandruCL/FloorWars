# Session C: read endpoints and Valkey leaderboards

**Name** `w3-c` | **Model** Sonnet 5.5 | **Effort** medium | **Branch** `feat/w3-read-api` | **Ports** db 55503, valkey 56503 | **Peers** `w3-a` (tables, `rolling_points`), `w3-b` (calls your helpers), `w3-lead`

Skills to load first: `token-saver`, `backend-conventions`.

Read: `Ionut/week3/spec.md` sections 1, 2, 6 to 9, 11; `contracts/openapi.yaml` paths `/buildings`, `/buildings/{id}/standings`, `/leaderboards` and schemas `Building`, `BuildingStandings`, `TeamStanding`, `Leaderboard`, `LeaderboardEntry`, `Team`; `server/app/valkey.py`, `server/app/api/deps.py`, `server/app/api/v1/teams.py` (pattern), `server/tests/conftest.py`, `helpers.py`.

## Start now (no new tables needed)

1. `app/leaderboards.py`: `record_verified`, `publish_flip`, `rebuild`, `top` (spec section 7) on top of the existing `valkey` client wrapper. Pure helper functions are unit-tested with a fake client; Valkey-backed tests use the test Valkey (`FLOORWARS_TEST_VALKEY_URL`). Commit, then message `w3-b`: `LEADERBOARDS READY <sha>`.
2. `GET /v1/buildings` and its tests (the `building` table exists since Week 1).

## After `w3-a` reports `A1 READY` and its PR is merged (merge `origin/main` into your branch)

3. `GET /v1/buildings/{id}/standings`: one query joining `building_claim`, the teams and `claim.rolling_points`; tests for owner, zero-point teams, the window edge, 404s, 401.
4. `GET /v1/leaderboards` for the three scopes, database fallback, lazy rebuild, tests. Write down the `scope=building` choice (spec section 8) in your report.
5. Router registration, PR, tell `w3-lead`: `C READY <PR number>`.

## Verify (from `server/`, own containers `fw-w3-c-db` 55503, `fw-w3-c-valkey` 56503)

`ruff check .`, `ruff format --check .`, `mypy app`, `pytest -q`. Summary lines only.

## Report (short)
Branch, commits, verify lines, the `scope=building` decision, open questions.
