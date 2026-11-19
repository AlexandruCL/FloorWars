# Prompt: Ionut's Week 4 implementation (FloorWars, server side)

**Status (2026-11-19): draft, the eight launch decisions answered by Ionut (section 4). Lines still marked `OPEN` are for the agents to raise; nothing uses a recommendation until Ionut answers. Facts checked against `main` at `4b02e9a`. Implementation not started.**

You are coordinating Ionut's part of Week 4 in `C:\Users\Ionut\Desktop\sem1_an4\msa\FloorWars`. Work on feature branches from `main`. Follow the checklist in section 3 in order, except where a step says it can run in parallel. Tick each box only after its verification command has run and passed.

Goal from the plan: *the loop is visible and social.*

Exit from the plan: *two phones on different teams: phone 1 climbs, phone 2's building standings flip live and phone 2 gets a notification. The barometer-less path works on a device or an emulator flag.*

Cristea's app side of Week 4 is merged on `main` and waits for this server work (`cristea/week_4/finish_week_4.md`, step 3). His app calls endpoints that do not exist on the server yet; section 1 lists them. That makes this week's server work the critical path.

## 0. Ground rules

- **Ionut takes every decision. You may not guess.** If this prompt, the plan, the contract, a recorded answer from Ionut or the existing code does not settle a choice, stop that item and ask Ionut with `Skill("grilling")`. Your recommendation goes with the question, and nothing uses it until Ionut answers. Look up facts yourself. Carry on with items that do not depend on the answer.
- **This prompt follows `IMPLEMENTATION_PLAN.md` and `contracts/openapi.yaml` 0.8.0-draft.** If you find a difference between them, stop that item and ask Ionut. An answer that changes the plan goes into the plan in the same PR (docs rule, plan 9.3).
- **Read only the docs in section 2.** Do not read Cristea's app code beyond the lines section 2 names, and do not read the plan for Weeks 5 and 6. If you need something outside the list, say which file and why before opening it.
- Load `token-saver` first, then `backend-conventions`. Targeted search before reading; files over 300 lines in ranges only; never print full logs or test output (`-q`, `tail`, `grep`).
- **Contract first.** The contract is the one Cristea's app is built against. Change `contracts/openapi.yaml` only in the lead's contract commit (W4-0), as a PR that Cristea reviews, and regenerate `app/src/api/schema.ts` with `npm run generate:api` in `app/` in the same commit. A server answer that differs from the contract is a bug in the server, not in the contract.
- **Do not break the app.** Every field name, status code and enum value the app reads is fixed by contract 0.8.0. The JSON of a `building_flipped` event is the one `leaderboards.flip_message` already writes (team codes, not ids): the socket, the replay and `GET /me/events` all use it.
- No new dependency without Ionut's approval. Name the candidates, their licence and last release date, and wait. Already installed and enough for this week (checked 2026-11-19): `fastapi`, `starlette` 1.9.0 (has `WebSocket.send_denial_response`, needed for the 401 on the upgrade), `uvicorn[standard]` 0.54.0 with `websockets` 17.3, `valkey` 6.2.0 (includes `valkey.asyncio`), SQLAlchemy 2.1 (sync `Session`).
- Data minimisation (plan 8): events carry the team code and the building only; no user id, e-mail or coordinates in any event, log line or response that is not the caller's own data.
- Branch per task, push it, one PR per branch into `main`; no direct push to `main`; merge commits, not squash; no Co-Authored-By or any other trailer. The lead merges after CI is green and its own checks pass.
- **VM and Azure actions are Ionut's only** (deploy, migrations on the VM, secrets, NSG, ufw). A session writes the steps; Ionut runs them.
- Before you claim any item done, run its verification command and paste the summary line into your report. No claim without output. If a root cause is unclear for a failing test, find it first, then fix.

## 1. Current state (checked 2026-11-19)

- **Week 3 server: merged and reviewed.** The `w3-f` findings Ionut chose to fix are merged (#69 to #72; `111527c` removed the local notes). Finding 15 (shared device id, receipts per user) was not changed: `repository.py` has no `RETURNING` receipt insert; W4-5 picks up its device-sharing part. Deployed on the VM: `fbe9c18` (2026-11-08). The later merges (#69 rejection cap, #70 audit fixes, #71 batched reads) are **probably not deployed**: W4-0 checks the release on the VM.
- **Contract 0.8.0-draft is merged** (Cristea's W4-0, `4b02e9a` updated the server test). It added `RejectionReason` (14 reasons), `reason` on `SegmentRecord`, `GET /seasons`, `event_id` required on both WS events, and "401 on the upgrade, never 403, never close after accept" for `WS /ws`.
- **Endpoints the contract has and the server does not** (`grep operation_id server/app/api/v1`): `listSeasons` (`GET /seasons`), `listMySegments` (`GET /me/segments`), `getSeasonStats` (`GET /me/season-stats`), `listMyEvents` (`GET /me/events`), `openWebSocket` (`WS /ws`), `createLandingScan` (`POST /landing-scans`). Also `getClassifierConfig`, `exportMyData`, `deleteMe`: those are Week 5, not this week.
- **What the app already does with them** (from `cristea/week_4/week_4_prompt.md`, binding for the server because the app is merged):
  - `GET /me/season-stats` gives `team_id`; the app maps it to a code with `GET /teams` and hands the code to the Kotlin notifier. **Without this endpoint no notification ever fires**, so it is not a landmarks nicety.
  - `GET /me/segments` feeds Home's `Verified today: {steps} steps, {metres} m` (sums `steps_scored` and `ascent_m` of `verified` items since local midnight, paging with `next_cursor`) and the History screen (50 per page, newest first, a sentence per `reason`).
  - `GET /seasons` feeds the leaderboard season selector, newest `starts_at` first.
  - The socket: one per app, owned by Kotlin, `Authorization: Bearer <token>`, `?since=<last id>`, ping every 30 s, reconnect 1 s doubling to 60 s with full jitter. A 401 on the upgrade stops it until JS hands over a new token. Duplicates are dropped by `event_id`. A connection or poll from `since=0` is a silent catch-up.
  - The poll: the 15-minute sync job calls `GET /me/events?since=<id>&limit=100`, at most 5 pages while `has_more`.
  - The notifier fires only for `building_flipped` with `from_team` equal to the player's team code, at most once per building per 10 minutes, on the phone.
  - Landing scan: needs an active check-in on the phone, sends `{qr_token, building_id, scanned_at}` with the token unchanged (at most 512 characters, no control characters), shows the server's `points` and computes none, cools down 10 minutes per building locally, honours `Retry-After` on 429. Messages per status: 201, 403, 422, 429.
- **What exists that this week builds on (reuse, do not duplicate):**
  - `game_event` table (migration `0004_segments`), written inside the claim transaction in `server/app/segments/claim.py` when an owner changes; `segments.models.Flip` carries `event_id`.
  - `server/app/leaderboards.py`: `EVENTS_CHANNEL = "fw:events"`, `publish_flip` (Valkey `PUBLISH` after the commit, best effort in `service._notify`), `flip_message` (the event JSON).
  - `server/app/qr_token.py`: entrance tokens `fwq1.<b64url(payload)>.<b64url(HMAC-SHA256)>`, `sign(building_id, key, nbf, exp)`; `tools/qr/` prints them.
  - `server/app/auth/ratelimit.py` (`Limiter`, `RateLimiter.hit`), `server/app/api/deps.py` (auth dependency, `problem_response`), `server/app/teams/` (`active_season`, `get_season`), `server/app/segments/` (rules, service, repository, claim, partitions).
  - `infra/docker-compose.yml`: **two API replicas** behind Caddy. A socket on one replica must receive flips committed on the other: that is what the Valkey fan-out is for.
- **Season has no `paused` column.** `season_state` events start with the Week 5 pause switch. The hub and the feed must pass a `season_state` row through if one exists, but nothing writes one this week.
- **Not this week (Week 5), do not drift into them:** admin panel, `config` table and `GET /config`, Celery jobs (partitions, retention, rollover), `GET /me/export`, `DELETE /me`, monitoring, backups, k6.
- **Server reachability:** on 2026-11-17 every request from Cristea's laptop to `api.floorwars.me:443` timed out (DNS resolved). Cause unknown. W4-0 settles it before anything is deployed.

## 2. Documents to read (and only these)

| Doc | Which part | Needed for |
|---|---|---|
| `IMPLEMENTATION_PLAN.md` | Section 10, "Week 4" (Ionut and exit lines) | All |
| `IMPLEMENTATION_PLAN.md` | Section 7.2.1 (notifications without Firebase) | W4-2, W4-3 |
| `IMPLEMENTATION_PLAN.md` | Sections 2 (game rules), 3.4 (anti-cheat layers), 5 (data model) | W4-1, W4-4, W4-5 |
| `IMPLEMENTATION_PLAN.md` | Section 8 (security and privacy), 7.10 (network failures) | All |
| `IMPLEMENTATION_PLAN.md` | Section 9.2, 9.3 (Week 4 row), 15.3 (two Week 4 rows) | W4-6, W4-7 |
| `contracts/openapi.yaml` | The six paths of section 1 and their schemas: `Season`, `SeasonStats`, `LandmarkProgress`, `SegmentPage`, `SegmentRecord`, `SegmentFields`, `RejectionReason`, `GameEventPage`, `WsEvent`, `BuildingFlippedEvent`, `SeasonStateEvent`, `BuildingFlip`, `LandingScanRequest`, `LandingScan`, `Problem`, the shared responses | All |
| `Ionut/week3/spec.md` | Sections 1 to 7 and 11 (they still hold for segments, claims, scoring, Valkey and the session rules) | W4-1, W4-4, W4-5 |
| `server/README.md` | Sections on auth, segments, leaderboards | All |
| `cristea/week_4/week_4_prompt.md` | Section 3, items W4-1, W4-3, W4-4 (only to confirm what the app sends and reads) | W4-1 to W4-4 |
| `docs/runbook.md` | Deploy and migration sections | W4-0, W4-7 |
| `.github/workflows/server.yml` | Whole file | All (CI must stay green) |
| Code | The files named in section 1 under "What exists", only the lines you need | All |

## 3. Checklist

### Plan coverage

| Plan line (section 10, Week 4; 9.3; 15.3) | Item |
|---|---|
| WebSocket hub in the API: auth on connect, Valkey pub/sub fan-out so two replicas share events | W4-3 |
| Notifications (7.2.1): `game_event` written in the claim transaction (exists since Week 3), replay on connect (`since`), `GET /v1/me/events`, per-user notification rate limit | W4-2, W4-3 |
| Pair with Cristea on the socket in the Kotlin service, the local notification and the deep link (Cristea built them in Week 4; the pairing is the live check) | W4-7 |
| Landmarks progress in `GET /v1/me/season-stats` | W4-1 |
| `POST /v1/landing-scans` with strict rate limits | W4-4 |
| Anti-cheat v2: per-device limits, repeated identical segments, impossible sequences, fraud flag reasons | W4-5 |
| Not in the plan's Ionut list, needed by Cristea's merged app: `GET /v1/seasons` (contract 0.8.0), `GET /v1/me/segments` (Home today figures, History) | W4-1 |
| 9.3, Week 4: phone 2 gets a notification when phone 1 flips a building | W4-7 |
| 15.3: accessible contribution mode rules; third person for the pilot | W4-4, W4-7 |
| Exit line | W4-7 |

Dependencies: W4-0 first. Then W4-1, W4-2 + W4-3, W4-4 and W4-5 run in parallel, one agent each in its own worktree. W4-3 uses W4-2's feed function for the replay; both are with one agent, so no wait. W4-4 and W4-5 both touch `server/app/segments/`; file ownership below keeps them apart. W4-6 (review) after the four code branches merge. W4-7 last.

### The seam (shared names, fixed; a change is a question for `w4-lead`)

```python
# server/app/events/feed.py (owner: w4-events) - the ONE filter and serializer, used by GET /me/events and the WS replay
def event_json(row: GameEvent, codes: Mapping[int, str]) -> dict[str, object]: ...
    # building_flipped: same keys and values as leaderboards.flip_message (team codes); season_state: type, event_id, paused, ends_at
def events_after(db: Session, user_id: uuid.UUID, since: int, limit: int) -> EventPage: ...
    # EventPage(items: list[dict], last_event_id: int, has_more: bool); ascending event_id; last_event_id == since when empty

# server/app/realtime/hub.py (owner: w4-events)
# One Valkey subscriber per process on leaderboards.EVENTS_CHANNEL, fan-out to the local sockets that may see the event.

# server/app/landing/ (owner: w4-landing)
def scan(db: Session, user_id: uuid.UUID, req: LandingScanIn, now: datetime) -> LandingScanResult: ...
    # runs inside the existing claim transaction path, so locks, team_building_score, building_claim, game_event and flips are the same as for segments

# server/app/qr_token.py (owner: w4-landing) - landing stickers are a separate kind inside the SIGNED payload
```

Rules for the seam:

- `event_json` is the only place that turns a `game_event` row into JSON, and its `building_flipped` output must equal `flip_message` for the same flip. A test asserts it.
- Who may see an event is decided in `events_after` and nowhere else; the hub applies the same predicate to live messages (decided in W4-2).


### 3.1 Subagents and worktrees

Decided (Ionut, 2026-11-19): Cristea's model. This session (`w4-lead`) coordinates: it writes the agent files, commits the contract, starts the agents with the Agent tool, puts their questions to Ionut, re-runs every check, merges, and does W4-0, W4-6 and W4-7 itself. It does not implement the delegated items.

| Agent | Items | Worktree, branch | Model, effort | Owns (one owner per file) |
|---|---|---|---|---|
| `w4-lead` (this session) | W4-0, W4-6, W4-7, merges | main checkout; `contract/w4-server`, `docs/w4-ionut-prompt` | Opus, high | `contracts/openapi.yaml`, `app/src/api/schema.ts`, merge conflicts in `server/app/api/v1/__init__.py` |
| `w4-read-api` | W4-1 | `<root>-w4/read-api`, `feat/w4-read-api` | sonnet, medium | `server/app/api/v1/{seasons,me}.py`, `server/app/me/*`, `server/tests/me/*` |
| `w4-events` | W4-2, W4-3 | `<root>-w4/events`, `feat/w4-events-hub` | opus, high | `server/app/events/*`, `server/app/realtime/*`, `server/app/api/v1/{events,ws}.py`, `server/tests/events/*`, `server/tests/realtime/*`, `infra/caddy/Caddyfile` (WS lines only) |
| `w4-landing` | W4-4 | `<root>-w4/landing`, `feat/w4-landing-scans` | opus, medium | `server/app/landing/*`, `server/app/qr_token.py`, `server/app/api/v1/landing.py`, the next migration, `server/app/segments/claim.py` and `repository.py` (only the scan lines), `server/app/leaderboards.py` (scan points in the update and the rebuild), `tools/qr/*`, `server/tests/landing/*` |
| `w4-anticheat` | W4-5 | `<root>-w4/anticheat`, `feat/w4-anticheat` | opus, high | `server/app/segments/{rules,service}.py`, `server/tests/segments/test_rules.py`, `test_anticheat.py` |
| `w4-docs` | docs and the e2e script for W4-7 | `<root>-w4/docs`, `docs/w4-server-status` | sonnet, low | `README.md`, `server/README.md`, `IMPLEMENTATION_PLAN.md`, `docs/*`, `tools/e2e/*` |

`<root>` is `C:/Users/Ionut/Desktop/sem1_an4/msa/FloorWars`. W4-6 uses the three existing reviewer agents (`claim-transaction-reviewer`, `privacy-security-reviewer`, `contract-guardian`); no new agent.

Order:

1. This session does W4-0: baseline, server state, the contract commit, and the five agent files.
2. Restart the session so the agents load (project agents load at session start).
3. Create the worktrees from `contract/w4-server` (so every agent builds on the 0.9.0 contract), then start `w4-read-api`, `w4-events`, `w4-landing`, `w4-anticheat` in parallel and `w4-docs` alongside.
4. W4-6 after the four code branches merge; W4-7 last.

Agent files (`.claude/agents/w4-*.md`, written by this session in W4-0; `.claude/` is gitignored, so they are local): frontmatter `name`, `description`, `tools` (Read, Grep, Glob, Edit, Write, Bash; the PowerShell tool on Windows), `model`. Body: the items it owns, its worktree and branch, the files it owns (table above), "read `<root>/Ionut/prompt_week4.md` by absolute path, sections 0, 1, 2, your items, the seam and section 4", the verify commands, and "you cannot ask Ionut: list questions under Blocked with your recommendation and carry on".

Rules for this session:

- Start each agent with the Agent tool. Give it the item IDs, its worktree path and the absolute path of this prompt.
- Agents may message each other for interface questions about the seam (SendMessage by agent name, if the tool is available to them; otherwise through this session). File ownership stays exclusive.
- Re-run each item's verify command yourself before you tick its box, and check that the tests fail when the rule they guard is broken. Agent reports are evidence, not proof.
- When an agent lists a Blocked question, ask Ionut with `Skill("grilling")`, record the answer in section 4, and send it back to the agent.
- The branch name `feat/w4-realtime` is Cristea's (merged). Do not reuse it.
- The router list in `server/app/api/v1/__init__.py` (`_FEATURE_ROUTERS`) is the expected merge conflict between `w4-read-api`, `w4-events` and `w4-landing`: resolve it by listing all routers. Merge order: read-api, events, landing, anticheat, docs.
- If `w4-landing` and `w4-anticheat` both need `repository.py`, `w4-anticheat` asks `w4-landing` first; the first to merge wins and the other rebases.
- Each agent uses its own Docker containers and ports (Postgres, Valkey) and stops them when done. Python: the literal venv path in "Verify commands".

Commands:

```
git worktree add <root>-w4/read-api  -b feat/w4-read-api      contract/w4-server
git worktree add <root>-w4/events    -b feat/w4-events-hub    contract/w4-server
git worktree add <root>-w4/landing   -b feat/w4-landing-scans contract/w4-server
git worktree add <root>-w4/anticheat -b feat/w4-anticheat     contract/w4-server
git worktree add <root>-w4/docs      -b docs/w4-server-status contract/w4-server
# for each worktree:
mkdir -p <worktree>/.claude && cp -r <root>/.claude/skills <root>/.claude/agents <worktree>/.claude/
```

Do not run `git checkout` in the main checkout in a way that loses work. Check `git worktree list` after each addition. If `contract/w4-server` turns out empty (no contract change), branch from `main` instead.

### Verify commands (used by every item)

CI's steps (`.github/workflows/server.yml`, checked 2026-11-19), run through the repo venv, because `uv` is not installed on this PC and a worktree has no venv of its own. From `server/`, with the session's Postgres and Valkey up (`PY` is `C:/Users/Ionut/Desktop/sem1_an4/msa/FloorWars/.venv/Scripts/python.exe`, written literally):

```
$PY -m ruff check . && $PY -m ruff format --check .
$PY -m mypy app
$PY -m pytest -q
$PY -m alembic upgrade head && $PY -m pytest -q ../tools/qr ../tools/seed
```

CI also validates the contract with `openapi-spec-validator` 0.9.0; the lead runs it only if it is in the venv (no install without Ionut's approval), otherwise CI is the check.

Contract-shape tests reuse the helper in `server/tests/auth/test_contract.py`.

### W4-0 Preflight and server state (first, lead)

- [ ] `git status`, `git branch --show-current`; `main` level with `origin/main`. List local changes; do not touch them.
- [ ] Baseline before any change: the verify commands on `main`, plus `cd app && npx jest __tests__/apiContract` (the generated client matches the contract). Record the summary lines. Pre-existing failures are listed, not fixed silently.
- [ ] Ionut, on his PC: `curl.exe -i https://api.floorwars.me/healthz`. If it times out from his network too, check (Ionut only) that the VM runs, the NSG allows 443 from anywhere, and ufw allows 443. Record the cause of Cristea's 2026-11-17 timeouts, or "not reproduced".
- [ ] Ionut, on the VM: which commit is deployed (`deploy.sh` status or the image tag). If it is `fbe9c18`, the Week 3 fixes #69 to #71 are not live yet; they go out with the first Week 4 deploy (W4-7).
- [ ] Contract commit on `contract/w4-server` (decided by Ionut, 2026-11-19), version 0.9.0-draft with a changelog line, `schema.ts` regenerated with `npm run generate:api`, Cristea reviews:
  - `GET /me/season-stats`: a `404` `Problem` when no `season_id` is given and no season is active (as `GET /seasons/active` has).
  - `POST /landing-scans`: the `403` description also covers "no check-in of the user at this building valid at the scan time"; `scanned_at` description says the server replaces a value more than 10 minutes old or 5 minutes ahead with its own time.
  - `GET /me/events` and `WS /ws` descriptions: events of every season the user has joined (not only flips involving the user's team).
  - No new `RejectionReason` (anti-cheat v2 is flag-only).
  Before committing, compare each of the six paths with what Cristea's app sends and reads (section 1). Anything else that would need a contract change is a question for Ionut now, so no second contract PR appears mid-week.
- [ ] Write the five agent files of section 3.1, then restart the session so they load. Create the worktrees from `contract/w4-server`.
- Verify: `cd app && npm run generate:api && npx jest __tests__/apiContract` on `contract/w4-server`, and the server verify commands (the server contract tests read `openapi.yaml`).
- Done when: the baseline is recorded, the server is reachable (or the cause is written down), the deployed commit is known, the contract commit passes, and the worktrees and agents exist.

### W4-1 Read endpoints the app already calls (`w4-read-api`)

- [ ] `GET /v1/seasons` (`listSeasons`): every season, newest `starts_at` first, `Season` shape as `GET /seasons/active` returns it today (reuse its serializer). 401 without a token.
- [ ] `GET /v1/me/segments` (`listMySegments`): the caller's `climb_segment` rows, newest `started_at` first, `limit` 1 to 100 (default 50), opaque `cursor` / `next_cursor` (null on the last page). Each item has exactly the `SegmentRecord` fields (`unevaluatedProperties: false`): the `SegmentFields`, `status`, `steps_scored`, `reason` (`reject_reason` for rejected, `null` otherwise). Keyset pagination on `(started_at, id)` so a new upload between two pages neither repeats nor skips a row. Uses the existing `(user_id, started_at DESC)` index; a test checks the plan with `EXPLAIN`.
  - OPEN: the contract allows `status: pending`, but the server stores only `verified` and `rejected`. Recommendation: never return `pending` (pending rows live only on the phone).
  - OPEN: rejected items past the 200-per-hour cap are not stored (Week 3 decision), so History cannot show them. Recommendation: accept it, write it in `server/README.md`.
- [ ] `GET /v1/me/season-stats` (`getSeasonStats`): `season_id` query, default the active season. No active season and none given: `404` `Problem` (contract 0.9.0, decided by Ionut 2026-11-19; Cristea's app should treat it as "no team" for the notifier, a note for his review). `team_id` (null without a membership), `steps_verified` (sum of `steps_scored` of verified segments of that season), `ascent_m`, `points`, `rank` (individual rank from the existing Valkey board, falling back to the database the way `GET /leaderboards` does; null when the user has no points), `buildings_owned_by_team`, `landmarks`.
  - Landmarks: a fixed list of `(name, height_m)` as named constants in one module; `reached` is `ascent_m >= height_m`. OPEN: which landmarks and heights. Recommendation: 4 to 6 entries from a cited source (for example the Eiffel Tower 330 m), checked by the session, sorted by height.
  - Landing-scan points (W4-4) count in `points` and `rank`; they add no `steps_verified` or `ascent_m`. Read them through `w4-landing`'s function (W4-4); until W4-4 merges, `points` is segments only and a test is marked to be extended.
- [ ] Tests: each endpoint's 200 shape validated against the contract schema (reuse the helper in `server/tests/auth/test_contract.py`), 401, empty results, paging stability with an insert between pages, `reason` null for verified, other users' rows never returned, season default, landmark boundary (`ascent_m` equal to a height is reached).
- Verify: the verify commands. Paste the summary lines.
- Done when: the tests pass, and they fail if another user's row is returned or the cursor repeats a row (break each once, check, revert).

### W4-2 Event feed `GET /v1/me/events` (`w4-events`)

- [ ] `events_after` (seam) and the route (`listMyEvents`): events with `id > since`, ascending, `limit` 1 to 100 (default 50), `last_event_id` = the highest id returned or `since` when empty, `has_more`. Items are `WsEvent` JSON from `event_json`.
- [ ] Who sees which event (decided by Ionut, 2026-11-19): **every event of every season the user has joined** (a `team_membership` row for the event's `season_id`), not only flips involving the user's team. Reason: Cristea's Standings screen refreshes on any flip of the building it shows, and flips are public game state (the standings endpoint already shows them). The phone still notifies only for the player's own team's losses. Plan 7.2.1 is updated to say so (`w4-docs`). The WS hub uses the same predicate.
- [ ] Per-user notification rate limit (plan 7.2.1). OPEN. Recommendation: no server-side drop. The phone already limits a notification to one per building per 10 minutes, and dropping events on the server would also hide them from the live standings. Record the decision in plan 7.2.1.
- [ ] Old events. `since=0` returns "the oldest kept events". OPEN: how long `game_event` rows are kept. Recommendation: keep all this week; the Week 5 retention job drops rows older than the season plus 30 days; write it in the runbook TODO.
- [ ] Tests: ascending order, `since` excludes equal ids, `limit` and `has_more` at the boundary, `last_event_id` when empty, the visibility predicate, `event_json` equals `flip_message` for the same flip, 401, a 422 for `limit=0` or `101`.
- Verify: the verify commands. Paste the summary lines.

### W4-3 WebSocket hub `WS /v1/ws` (`w4-events`)

- [ ] Auth on the upgrade: `Authorization: Bearer <token>` (what the app sends) or the `access_token` query. A missing, expired or invalid token answers **HTTP 401 on the upgrade** with `WebSocket.send_denial_response` (Starlette 1.9.0 has it; check that uvicorn with `websockets` 17.3 passes it through), never 403 and never a close after accept (contract 0.8.0). A test opens the socket with a bad token and asserts status 401.
  - OPEN: a token that expires while the socket is open. Recommendation: auth on connect only; the socket stays open (the contract forbids an auth close after accept, and Cristea's service would otherwise stall in the background until JS runs). Write it in `server/README.md`.
  - OPEN: the access token in the `access_token` query ends up in Caddy and uvicorn access logs. Recommendation: keep the query for the contract, but make sure neither logs the query string of `/v1/ws` (check the Caddy log format and the uvicorn access log config).
- [ ] Replay then live, with no gap and no loss: on connect, **subscribe first** (or register with the process hub), then run `events_after(since)` page by page and send each, remember the highest id sent, then forward live messages and drop any live `event_id` at or below it. A test commits a flip between the replay query and the live phase and checks it arrives exactly once.
- [ ] Fan-out: one Valkey subscriber per process on `leaderboards.EVENTS_CHANNEL` (`valkey.asyncio`, already installed), started with the app's lifespan, forwarding each message to the local sockets that may see it (W4-2's predicate). Not one Valkey connection per socket. Two app instances in one test (or two hubs on one Valkey) prove a flip published by one reaches a socket on the other.
- [ ] The predicate needs the event's season, which `flip_message` does not carry. Load the user's joined season ids once at connect; add `season_id` to the **internal** Valkey message (`publish_flip`) and strip it before sending to the socket, so the event JSON stays exactly the contract's. A test checks the socket never receives `season_id`. No database query per message per socket.
- [ ] Database access from the async handler: the app uses a sync `Session`. Run the replay in a thread (`run_in_threadpool`) with its own session, closed before the live phase. Never hold a database connection for the life of a socket (the pool has 20).
- [ ] A publish that fails after the commit (best effort in `service._notify`) means live sockets miss that flip until they reconnect; the phone's 15-minute poll catches it. Accept and document; do not add a retry queue this week.
- [ ] Limits. OPEN: sockets per user. Recommendation: at most 3 per user per replica, the oldest closed with code 1008 when a 4th opens; and a send that blocks (slow client) drops that socket rather than the hub. The server sends no pings of its own; it answers the client's pings (the `websockets` library does this).
- [ ] Caddy: confirm `reverse_proxy` passes the upgrade and does not cut idle sockets under 60 s (the client pings every 30 s). Change `infra/caddy/Caddyfile` only if a test against the local compose stack shows it is needed.
- [ ] Tests: 401 on the upgrade (missing, expired, wrong signature) with no accept; bearer and query both accepted; replay from `since`, then live; no duplicate across the replay-live edge; `since` above every id sends nothing until a live event; fan-out across two hubs; the visibility predicate on live messages; the per-user socket cap; the replay session is closed before the live phase.
- Verify: the verify commands. Paste the summary lines. Also once against the local compose stack (`infra/compose.local.yml`, 2 replicas behind Caddy): a socket opened through Caddy receives a flip uploaded with `tools/fake_segments` through the other replica.
- Done when: the tests pass, and they fail if the subscribe-before-replay order is reversed or the live dedupe is removed (break each once, check, revert).

### W4-4 Landing scans `POST /v1/landing-scans` (`w4-landing`)

- [ ] Sticker token (decided by Ionut, 2026-11-19): the entrance-token scheme of `qr_token.py` with a `kind: "landing"` claim **inside the signed payload** and the prefix `fwl1.`, the same signing key (no new secret). The entrance verifier refuses a token with a `kind` claim and the landing verifier requires `kind: "landing"`, so neither code scores as the other. `nbf`/`exp` as for entrance codes (at most 31 days). At most 512 characters (the app's limit). `tools/qr/make_entrance_qr.py` prints them (one CLI flag, same output as the entrance codes).
- [ ] Request: `LandingScanRequest` strict (`additionalProperties: false`). `building_id` must equal the token's building, else 403. Token invalid or outside its window: 403. Body not valid: 422.
- [ ] Check-in (decided by Ionut, 2026-11-19): required. The user needs a check-in at that building valid at `scanned_at`, the same rule as segments; otherwise `403` (contract 0.9.0 widens the 403 text). The app's 403 message ("This sticker isn't for this building, or it has expired.") stays; Cristea decides whether to add a sentence.
- [ ] `scanned_at` (decided by Ionut, 2026-11-19): optional per the contract; when missing, or more than 10 minutes old, or more than 5 minutes ahead, the server uses its own time and accepts the scan (no 422, because the app shows "This code isn't a FloorWars stair sticker." for a 422, which is wrong for a clock problem). Both bounds are named constants.
- [ ] Points (decided by Ionut, 2026-11-19, plan 15.3 accessible contribution mode): `LANDING_SCAN_POINTS = 20` (about one floor-equivalent), a named constant, counted in `team_building_score`, in the 7-day ownership recompute and on the leaderboards like verified segments, so a barometer-less player can help flip a building. That needs a table `landing_scan` (new migration, expand-only; user, building, season, team, checkin, points, `scanned_at`, `created_at`) and `recompute_owner` summing both sources in the window.
  - Scan points must reach every reader of points, or a rebuild silently drops them (the Week 3 finding 6 pattern): the incremental Valkey update **and** `leaderboards.rebuild`, which today sums only `climb_segment` (`server/app/leaderboards.py`, the three `SELECT ... FROM climb_segment` queries); the standings reads; `points` and `rank` in season-stats. `w4-landing` owns these lines in `leaderboards.py` and `repository.py` and exposes one function for a user's scan points in a season; `w4-read-api` calls it for season-stats. A test checks that a rebuild equals the incremental boards with scans present.
- [ ] Rate limits (strict, plan): OPEN values. Recommendation: one scan per user per building per 10 minutes (matches the app's cooldown), 6 per user per hour, both in Valkey through the existing limiter; 429 with `Retry-After`. Valkey down: 503 (fail closed, as segments).
- [ ] The claim path: a scan with points goes through the same locks and the same claim transaction as a segment, writes `game_event` on a flip, publishes it after the commit, updates the leaderboards, and returns the flips in `LandingScan.flips` (same `BuildingFlip` shape as `POST /segments`).
- [ ] Idempotency. OPEN: the contract has no `Idempotency-Key` on this path. Recommendation: none; the 10-minute rate limit makes a retried scan a 429, which the app shows as a cooldown.
- [ ] Tests: entrance token refused as a sticker and sticker refused at `POST /checkins`; tampered payload; wrong building; expired; no check-in; each rate limit and `Retry-After`; points credited once; a scan that flips a building writes `game_event` and returns the flip; concurrency with a segment upload in the same building leaves one consistent owner (reuse the Week 3 concurrency test pattern); response matches `LandingScan`.
- Verify: the verify commands, plus `alembic check` (migration matches the models) and the migration up and down once on a fresh database. Paste the summary lines.
- Done when: the tests pass, and they fail if the `kind` check is removed (break once, check, revert).

### W4-5 Anti-cheat v2 (`w4-anticheat`)

Plan: *per-device limits, repeated identical segment detection, impossible-sequence checks (climbs in two buildings too close in time), fraud flag reasons.*

- [ ] **Flag only** (decided by Ionut, 2026-11-19): each new check writes a `fraud_flag` with a new rule name and the segment keeps its status and points. No new rejection reason, no contract change; an admin reviews flags in Week 5. Reason: the thresholds are guesses until pilot data exists, and a wrong reject costs an honest player points. Revisit after the pilot.
- [ ] Per-device limit: OPEN value. Recommendation: a flag `device_burst` when one `device_id` sends more than 60 batches in an hour (the per-user 429 bucket stays as it is), plus a flag `device_shared` when one `device_id` uploads for more than one user in a day (device sharing, review finding 15). Flag only, as decided above.
- [ ] Repeated identical segment: the same user has a verified segment with the same `steps`, `ascent_m` (to 0.01 m) and `duration_s` (to 0.1 s) in the last 7 days. OPEN tolerance; recommendation as written. Rule name `identical_segment`.
- [ ] Impossible sequence: two segments of the same user in different buildings where the time between the end of one and the start of the other is shorter than the walking time between the two buildings (footprint distance with PostGIS `ST_Distance` on geography, divided by a named `MAX_WALK_SPEED_MPS`, OPEN value, recommendation 2.0). Rule name `impossible_sequence`. Checked on both sides of `started_at` (the Week 3 out-of-order lesson, finding 1).
- [ ] All three run under the user lock with the batch's existing single reads (the Week 3 batch cost budget of 120 statements for a 100-item batch must still pass; `tests/segments/test_batch_cost.py`).
- [ ] Tests: each check at its boundary on both sides; out-of-order uploads; a flag is written once per segment and rule; a flagged segment keeps `verified` and its points; the response carries no new reason; the batch cost test.
- Verify: the verify commands. Paste the summary lines.
- Done when: the tests pass, and they fail if the both-sides check of `impossible_sequence` is reduced to backward only (break once, check, revert).

### W4-6 Independent review (this session, read-only agents, after W4-1 to W4-5 merge)

- [ ] This session starts three reviewers in parallel, the existing agents in `.claude/agents/`: `claim-transaction-reviewer` (landing scans in the claim path, anti-cheat under the lock), `privacy-security-reviewer` (WS auth, token in the query, event visibility, sticker tokens, rate limits), `contract-guardian` (every new path against contract 0.8.0 or 0.9.0, `schema.ts`).
- [ ] Output: a findings list ranked by severity, each with file and line, a failure scenario and a proposed fix, written to `Ionut/week4_review_findings.md` (local notes, not committed). Ionut decides which are fixed this week; the fixes are branches like any other.
- Done when: the findings file exists and Ionut has marked each finding.

### W4-7 Deploy, the pair check and the exit (lead with Ionut and Cristea, last)

- [ ] Integration: merge all code branches into a local throwaway branch and run the verify commands on it before the last PRs merge.
- [ ] Deploy (Ionut only, on the VM, steps written by `w4-docs` in the runbook): back up the database, pull, run the new migration with the migrator role, run the partition CLI, deploy, `curl.exe -i https://api.floorwars.me/healthz`, then the four checks of `cristea/week_4/finish_week_4.md` step 3 (`/healthz` 200; `/v1/seasons`, `/v1/me/events`, `POST /v1/landing-scans` 401 without a token, not 404).
- [ ] `tools/e2e/e2e_check.py` (updated by `w4-docs`): sign-in, `GET /seasons`, `GET /me/season-stats`, `GET /me/segments`, `GET /me/events`, a WS connect with replay, and with `--upload` a fake flip seen on the socket. Run once against the VM.
- [ ] Stickers: print one landing sticker per building (`tools/qr`), valid on the test days, and give Cristea the points per scan.
- [ ] **9.3, Week 4 (pair with Cristea):** phone 1 flips a building; phone 2 gets a notification. Twice: phone 2's app open, and phone 2 swiped away with no check-in (the 15-minute poll; note the delay). Cristea's phones, run together. Not claimed until both of you see it.
- [ ] **Exit (Cristea's phones, with Ionut):** SM-S918B and SM-G985F on different teams in the active season; SM-G985F on the Standings screen; SM-S918B climbs until its team owns the building; SM-G985F's owner colour flips live and it gets `{team} took {building}`, and the tap opens the standings. The barometer-less path once on a phone with the debug flag against the real server, using the printed sticker.
- [ ] Record the two plan 15.3 decisions: accessible mode (Ionut's points per scan, Cristea's position already in the plan), third person for the pilot (Cristea: no; Ionut's answer).
- [ ] Docs (`w4-docs`, lead checks): README "Backend, week 4" row and dated decisions, `server/README.md` sections for the new paths and the socket, plan 7.2.1 and section 10 for anything that changed, the runbook deploy steps and the `game_event` retention TODO. Write `Ionut/week4_summary.md`.
- Done when: each PR's CI is green, the deploy is verified, and the pair check and exit are done or listed with what blocks them.

## 4. Report format

After each item, one line: `W4-n done | verify: <command> → <summary line> | commit: <sha>`. Agents post the same line in their reports; the lead copies it here after re-running the verify command. Keep these sections up to date:

- **Blocked:** one line each, the question and the recommendation. Expect at least: the OPEN items still open; Cristea's review of the 0.9.0 contract commit (and whether his app treats the season-stats 404 as "no team"); Cristea's phones for W4-7; the cause of the 2026-11-17 timeouts.
- **Blocked, also expected:** the third person for the pilot (plan 15.3; Cristea's position is "no", Ionut's answer pending).
- **Decisions:** Ionut's answers only, one line each, dated, with the reason. Already decided (2026-11-19):
  - Execution: Cristea's model, one coordinating session with five `w4-*` subagents in worktrees (section 3.1); reviews by the three existing reviewer agents.
  - Event visibility: every event of every season the user has joined, on `GET /me/events` and the socket alike. Reason: the live Standings screen needs flips between other teams; flips are public game state.
  - Anti-cheat v2 is flag-only: new `fraud_flag` rule names, no new rejection reason, no contract change. Reason: thresholds are guesses until pilot data.
  - Landing sticker: `fwl1.` prefix, `kind: "landing"` inside the signed payload, same key as entrance codes.
  - Landing scan points: `LANDING_SCAN_POINTS = 20`, counted in team scores, the 7-day ownership window and the leaderboards.
  - `GET /me/season-stats` with no active season and no `season_id`: 404 `Problem`, added in contract 0.9.0.
  - Landing scan needs a valid check-in at that building: 403 otherwise, 403 text widened in contract 0.9.0.
  - Landing scan `scanned_at` more than 10 minutes old or 5 minutes ahead: replaced by the server time, not refused.
  You make no entries of your own.
- **Pair and phone checks:** only items run with Cristea's phones (W4-7). Not claimed until done.
- **Surprises from the deploy and the pair check:** field names, time zones, auth edges.

## 5. Exit for Week 4 (server side)

- `GET /seasons`, `GET /me/segments`, `GET /me/season-stats` (with landmarks), `GET /me/events`, `WS /ws` and `POST /landing-scans` answer as contract 0.9.0 says, tested, deployed and checked with `tools/e2e/e2e_check.py`.
- A flip committed on one replica reaches a socket on the other; replay plus live loses and repeats nothing.
- Anti-cheat v2 runs inside the batch budget and flags the three cases without rejecting.
- The two-phone check and the exit are done with Cristea, or listed with what blocks them.
- Every row of "Plan coverage" is done, or listed as waiting with its reason.
