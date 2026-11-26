# Week 4 review findings (W4-6, local notes, not committed)

Reviewed 2026-11-21 on `tmp/w4-integration` (all W4 code branches + stats branch merged; 743 passed).
Reviewers: claim-transaction-reviewer, privacy-security-reviewer, contract-guardian. Critical: none. High: none.
Ionut marks each: fix now / later (week) / accept.

| # | Sev | Where | Finding | Proposed fix | Ionut |
|---|---|---|---|---|---|
| 1 | Medium | `segments/rules.py:81-92`, `service.py:353`; served by `api/v1/me.py:34` | A `speed`-rejected segment is stored with the client's `vert_speed_mps` unchecked (negative, or infinite: a huge integer becomes `inf`). `GET /me/segments` then returns a value outside `SegmentRecord.vert_speed_mps` (`minimum: 0`): a negative number, `null`, or a 500 that breaks that History page for good (the app retries 5xx). Lead-confirmed: no bound on `vert_speed_mps` before `_check_physics`. Pre-existing storage (Week 3), newly exposed by W4-1. | Store a `speed` rejection only when the value is finite and >= 0, else receipt only (like the other range reasons); one `/me/segments` contract test with such a row. Check prod: `SELECT count(*) FROM climb_segment WHERE vert_speed_mps < 0 OR vert_speed_mps IN ('NaN','Infinity','-Infinity')`. | fixed 2026-11-21 |
| 2 | Low | `infra/caddy/Caddyfile:69-80` | Caddy's error logger (`http.log.error`, e.g. a 502 while both replicas restart) may log the full URI with `access_token`; the filter covers only the access log. Unverified. | Check on the local stack (stop api, connect `/v1/ws?access_token=x`, grep Caddy output); if seen, add the same filter to `log default` in the global options. | leak confirmed on local stack, fixed 2026-11-21 (2ac34ac) |
| 3 | Low | `realtime/logs.py:11,17` | Redaction matches only literal `access_token=`; `?access%5Ftoken=<jwt>` authenticates (Starlette decodes the key) and is logged in clear. Only hand-built clients (the app sends the header). | Match `access(?:_|%5[Ff])token=` case-insensitively; one test case. | fixed 2026-11-21 |
| 4 | Low | `landing/service.py:143-155` | The per-building 10-minute token is taken before insert/score/recompute/commit; a DB error after it costs the user the scan and a 429 for 10 minutes. (Both claim and security reviewers.) | Give the token back best-effort on an exception after `_take`, or accept and note it in `server/README.md`. | fixed 2026-11-21 (f1f9db9) |
| 5 | Low | `migrations/versions/0006_landing_scan.py:75-77` | Downgrade drops `landing_scan` but `team_building_score`, `building_claim` and `game_event` keep scan effects. | Docstring + runbook: a downgrade needs a manual recompute (expand-only policy; downgrades are not used in deploys). | later (note) (2026-11-21) |
| 6 | Low | `contracts/openapi.yaml` 439, 495, 1199-1205 | Server bounds the contract does not state: `season_id`/`building_id` <= 2^31-1, `since` <= 2^63-1, `qr_token` <= 4096 chars (422). App unaffected. | Additive bounds in contract 0.9.0 (PR #82, before Cristea's review). | fixed 2026-11-21 |
| 7 | Low | docs branch `IMPLEMENTATION_PLAN.md:315` | Section 6 row says `/me/events` is "for the player's team"; contract says every joined season. | Reword in PR #90; rebase #90 on the contract head. | fixed 2026-11-21 |
| 8 | Nit | `landing/service.py:137`, `api/v1/landing.py:33-36` | Stale `TODO(blocked)`; 403 text in generated docs omits `season-inactive`, `no-team`. | One-line edits. | fixed 2026-11-21 |

Missing tests (claim reviewer): same-team scan vs batch race (shared `team_building_score` row); assert `team_building_score` equals the sum over `POINTS_SOURCE`; a two-building batch racing a scan (claim-lock order).

Notes for later (not defects): Week 5 export must include `landing_scan`; a future check-in cleanup must handle `landing_scan.checkin_id`; W4-7: one bad-token WS connect through Caddy on the VM must give 401.
Fix commits: 1 d18b947 (#86), 2 2ac34ac + 3 87bb479 (#88), 4+8 f1f9db9 (#84), 6 3d3298a (#82), 7 82942cb (#90). Integration after fixes: 771 passed.
