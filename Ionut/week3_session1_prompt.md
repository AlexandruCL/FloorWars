# Session 1 prompt: quick fixes (A) then scoring (B)

Paste everything below the line into a fresh Claude Code session in the FloorWars repo (main checked out).
Local notes, not for GitHub. Delete after the fixes are merged.

---

Read Ionut/week3_review_findings.md (local notes, do not commit it, do not push it). This is SESSION 1 of 2. You own groups A (quick fixes) and B (scoring). Another session owns group C (leaderboards: findings 5, 6, 7, 11, 16, 18, 23). Do not touch those findings. The "Decisions already made" section of the notes is final; do not re-open it.

## Skills (invoke with the Skill tool, don't skip)
- Before any backend code: `backend-conventions` and `web-backend`.
- Before touching scoring, plausibility or ownership code (group B): `scoring-rules`.
- After each group changes an endpoint, table, env var, threshold or rule: `docs-sync`.
- `token-saver` throughout: targeted greps and line ranges, no log dumps.
- Before finishing each PR: `code-review` at the default level, then `simplify` on the diff.

## Agents (use them; run in parallel when files don't overlap)
Give every agent the shared spec as context, and let them message each other.
- Inspect phase: one `Explore` agent per group (A, B) to confirm each finding still holds on current main and to collect the exact lines. They are read-only.
- Implement phase:
  - One agent owns `service.py`. All edits to it go through that agent, group A first, then B.
  - One agent for the migration (finding 8) and the database tests.
  - One agent for `infra/caddy/Caddyfile` and the docstring (finding 10).
  - One agent for `contracts/openapi.yaml`, the client regeneration and the docs (finding 3 and the spec changes).
- Review phase, in parallel on every group's diff: `claim-transaction-reviewer`, `contract-guardian`, `privacy-security-reviewer` (for the body limit in 10), `code-reviewer`.
- Use `log-miner` for long test or migration output instead of reading it yourself.
- No agents for trivial one-line edits.

## Workflow
1. Inspect: run the Explore agents. Verify each finding against current main. Skip any that no longer hold and say so.
2. Write a short shared spec before any code:
   - the new rejection reason for finding 3 (suggest `overlap`),
   - the exact wording of the amended spec rule 8 (both-sided window),
   - the file ownership map from the Agents section.
3. Show me the spec and the branch/PR split, then WAIT for my approval.
4. Implement after approval. One branch per group (A, then B), one PR per branch, push each branch. No Co-Authored-By or other trailers. I or Cristea merge.
5. After PR A is pushed, tell me clearly: "A is ready, you can start session 2 once it is merged." Session 2 depends on A being merged.

## Group A. Quick fixes (2, 4, 8, 10, 13, 17)
- 2: `rules.storable_real(item.stair_prob)` guard plus a test with `1e-50`.
- 4: rebuild only when the key is missing; 404 for an unknown season or building; empty list for a building with no points. Keep this change small and local to the read path, because session 2 will rework the same area (marker key from finding 6). Do NOT add the `built` marker here.
- 8: new migration with the three indexes from the notes. Do not edit `0004_segments.py`.
- 10: Caddy `request_body { max_size ... }` (pick a sensible size and tell me what you chose) and fix the docstring in `api/v1/segments.py`.
- 13: cap building and leaderboard ids at 2147483647.
- 17: catch the leaderboard-update failure after commit, call `logger.exception`, return success. Keep it as one `try/except` around the existing call; session 2 will restructure it later.

## Group B. Scoring (1, 3, and 12 since it is the same code path)
- 1: count verified steps on both sides of `started_at` under the user lock. Amend spec rule 8. Add a test that replays 60 single-climb newest-first uploads and asserts that the points stay near the honest-play total.
- 3: reject a climb whose `[started_at, started_at + duration)` overlaps a verified climb of the same user, checked under the lock. Add the new reason, update `contracts/openapi.yaml`, regenerate the client, update spec section 4.
- 12: check `(id, started_at)` right after the receipt lookup, before the rules.
- Skip 15. It changes decision 1 (receipts per user, not per device). Ask me first.
- Do not edit the leaderboard-update section of `service.py` (around lines 240-246 and 288); that belongs to session 2.

## Group D. Only if time allows
Findings 9 and 14. Report a plan for each and wait for my go-ahead.

## Rules
- Run targeted tests per group, then the full suite once at the end. Report failures with the relevant output only.
- Do not run installs, downloads or deletions without asking me.
- Final summary per PR: changed files, tests run, review findings and how you resolved them, assumptions, risks. Keep it short.
