# Session E: documentation and plan alignment (lightest)

**Name** `w3-e` | **Model** Sonnet 5.5 | **Effort** low | **Branch** `docs/w3-status` | **No containers** | **Peers** `w3-lead`

Skills to load first: `token-saver`, `docs-sync`.

Read: `Ionut/week3/spec.md` sections 1 to 4 and 7 to 9; `IMPLEMENTATION_PLAN.md` sections 2, 3.1, 5.1 to 5.3 and Week 3 (Grep for headings); `README.md` Status, Decisions taken and Open work; `docs/runbook.md` section 12 (staging); `server/README.md` headings.

## Tasks (small, mostly edits)

1. **Plan alignment** (`IMPLEMENTATION_PLAN.md`): 5.1 gets `segment_receipt`, the partitioned key `(id, started_at)`, `team_id` and `season_id` on `climb_segment`, `building_claim.team_id` nullable, `fraud_flag` without a foreign key to `climb_segment`, `game_event` columns; 5.2 CHECK `steps_scored BETWEEN 0 AND 2000`; section 2 states that ownership uses the rolling 7 days and the tie rule, and the new rejection reasons; 3.1 step 8 to 10 match spec section 5. Keep each change to the lines it needs.
2. **README**: dated decision rows for 2026-11-07 (the five decisions of spec section 1), and the Week 3 line in Status only as "in progress" until the others merge.
3. **Runbook**: add a short "Week 3 deploy" part: the deploy runs `0004_segments` through the `migrate` service, `btree_gist` already exists, the partition CLI is run by the migrator (`docker compose ... run --rm migrate python -m app.segments.partitions`), the leaderboards are rebuilt after a Valkey restart (`rebuild`), the "Wednesday check" steps for Ionut: deploy, seed, one real climb, then three read-only SQL checks (count of `climb_segment` by status, `building_claim`, `team_building_score`) run through Run command with `psql` inside the postgres container as `postgres` (read-only, no DML on app tables).
4. `docs-sync` checklist, then push, PR, tell `w3-lead`: `E READY <PR number>`.

## Verify
Links and file names exist (`grep` for each path you mention), no mention of floors as a game unit, no secrets.

## Report (short)
Branch, commits, which plan sections changed.
