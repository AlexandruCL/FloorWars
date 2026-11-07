# Session F: independent review (start only after A, B and C are merged)

**Name** `w3-f` | **Model** Opus 5.5 | **Effort** high | **Branch** none (read-only; reports in the chat and one `docs/w3-review` PR if Ionut asks) | **Ports** db 55505, valkey 56505 | **Peers** `w3-lead`

Skills to load first: `token-saver`, `code-review`, `security-review`.

Read: `Ionut/week3/spec.md`; the merged code under `server/app/segments/`, `server/app/leaderboards.py`, `server/app/api/v1/{segments,buildings,leaderboards}.py`, `server/migrations/versions/0004_segments.py`; `infra/sql/roles.sql`.

## Review with three subagents in parallel (project agents live in `.claude/agents/`, local to this checkout; if a type is missing use `general-purpose` with the same brief)

1. `claim-transaction-reviewer`: the claim transaction, locking order and deadlocks (batches touching buildings A then B and B then A), the user-row lock, idempotency across retries and partition boundaries, the 7-day ownership recompute and tie rule against spec section 1, scoring correctness (the points formula at 299/300/301 steps with earlier steps), `game_event` written in the same transaction, partitions at a month boundary, the receipt and segment consistency when a transaction rolls back.
2. `privacy-security-reviewer`: abuse of the upload endpoint (spoofing another user's check-in, another device id, huge numbers, NaN and infinity, replays across users, rate-limit evasion by many small batches, plus/IPv6 handling already in auth), data minimisation (no raw streams, no coordinates), responses that leak other users' data, SQL built from input, grants of `floorwars_app` on the new tables, `ON DELETE CASCADE` paths and account deletion later.
3. `general-purpose` for performance: `EXPLAIN (ANALYZE)` of the owner recompute, the standings query and the 10-minute and 60-minute step sums on a test database filled with about 100k synthetic segments over three partitions (generate them with SQL in the test database only); report plans and timings, flag sequential scans.

Return one list ranked by severity with file:line and a concrete fix each. Do not edit code. Ionut decides which findings become a fix branch.
