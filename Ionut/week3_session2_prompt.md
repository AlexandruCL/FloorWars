# Session 2 prompt: leaderboards (C)

Start this session only AFTER session 1's PR A (quick fixes) is merged into main. Ideally run it in its own worktree (`claude --worktree` or EnterWorktree) branched from the updated main.
Paste everything below the line. Local notes, not for GitHub. Delete after the fixes are merged.

---

Read Ionut/week3_review_findings.md (local notes, do not commit it, do not push it). This is SESSION 2 of 2. You own group C (leaderboards): findings 5, 6, 7, 11, and 16, 18, 23 only if trivial once the rest is in. Session 1 owns scoring and quick fixes (findings 1, 2, 3, 4, 8, 10, 12, 13, 17). Do not touch those. The "Decisions already made" section is final: leaderboard findings 5, 6, 7, 11 are solved today, not in Week 5.

First check `git log` on main: PR A from session 1 (findings 2, 4, 8, 10, 13, 17) must already be merged. If it is not, stop and tell me. PR B (scoring) may or may not be merged. If it is not, expect conflicts in `service.py` and keep your edits there to the leaderboard-update section only (around lines 240-246 and 288), then rebase onto main before opening the PR.

## Skills (invoke with the Skill tool, don't skip)
- Before any backend code: `backend-conventions` and `web-backend`.
- `token-saver` throughout: targeted greps and line ranges, no log dumps.
- After the changes: `docs-sync` (spec, `IMPLEMENTATION_PLAN.md`, README).
- Before finishing the PR: `code-review` at the default level, then `simplify` on the diff.

## Agents (use them; run in parallel when files don't overlap)
Give every agent the shared spec as context, and let them message each other.
- Inspect phase: one `Explore` agent to confirm findings 5, 6, 7, 11 still hold on current main (including what session 1's PR A changed in the read path from finding 4) and to collect exact lines. Read-only.
- Implement phase:
  - One agent owns `leaderboards.py` (lock, marker, atomic updates, rebuild).
  - One agent owns the `service.py` leaderboard-update section and the account-deletion path (finding 11).
  - One agent for the tests (Valkey flushed mid-season, failed update then read, rebuild racing an upload).
  - One agent for the docs and spec notes.
- Review phase, in parallel on the diff: `claim-transaction-reviewer` (Valkey, locking), `privacy-security-reviewer` (finding 11 deletion), `code-reviewer`, `contract-guardian` (only if an endpoint changes).
- Use `log-miner` for long test output.
- No agents for trivial one-line edits.

## Workflow
1. Inspect with the Explore agent.
2. Write a short spec before any code:
   - Valkey keys: `fw:lb:s{season}:built` marker, the rebuild lock key, lock expiry value, how the upload waits on the lock (and the maximum wait before it gives up and marks the season "needs rebuild").
   - "Needs rebuild" = the `built` marker is deleted.
   - How finding 11 is done (remove user from the season's boards on deletion, or leave it to the rebuild and note it in the spec).
   - The file ownership map from the Agents section.
3. Show me the spec, then WAIT for my approval.
4. Implement after approval on one branch (e.g. `fix/w3-leaderboards`), one PR, push it. No Co-Authored-By or other trailers. I or Cristea merge.

## Group C. Leaderboards
- 5: Valkey lock (`SET NX` with a short expiry) around the rebuild. The upload's update waits on the same lock.
- 6: `fw:lb:s{season}:built` marker, set by the rebuild. Reads check it and rebuild if it is missing. Uploads skip updating a board that has no marker. Keep session 1's rule from finding 4: an existing board is not rebuilt on every read, and a building with no points returns an empty list, not a rebuild.
- 7: a separate `try` for flips; the per-segment updates in one `MULTI/EXEC` transaction; on failure delete the marker so the next read rebuilds. This replaces the single `try/except` that session 1 added for finding 17: keep the "never return 500 after commit, log with `logger.exception`" behaviour.
- 11: remove the user from the season's boards on account deletion if that is simple. Otherwise the rebuild removes them and the note goes in the spec.
- 16, 18, 23: only if trivial now. 23 is one `GROUPING SETS` scan instead of three scans; 16 is a pipeline per request. 18 depends on finding 22, so skip it.
- Tests: Valkey flushed mid-season then an upload then a read returns the full board; a failed Valkey update followed by a read repairs the board; a rebuild racing an upload neither double-counts nor loses points; the unknown-season 404 and empty-building cases from session 1 still pass.

## Rules
- Run targeted tests first, then the full suite once at the end. Report failures with the relevant output only.
- Do not run installs, downloads or deletions without asking me.
- Final summary: changed files, tests run, review findings and how you resolved them, assumptions, risks. Keep it short.
