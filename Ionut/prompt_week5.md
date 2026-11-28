# Prompt: Ionut's Week 5 implementation (FloorWars, server and ops side)

**Status (2026-11-28): draft. Facts checked against `main` at `8a58995`. Lines marked `OPEN` wait for Ionut; the launch decisions (section 4, "Launch questions") are asked before any worktree, agent file or code branch exists. Implementation not started.**

You are coordinating Ionut's part of Week 5 in `C:\Users\Ionut\Desktop\sem1_an4\msa\FloorWars`. Work on feature branches from `main`. Follow the checklist in section 3 in order, except where a step says it can run in parallel. Tick each box only after its verification command has run and passed.

Goal from the plan: *feature complete and operable.*

Exit from the plan: *an admin can create a season and a building from the panel without SQL; Grafana shows live metrics; a share card exports from a real session; one backup restore proven.*

Week 4's server code is merged (#82 to #92), but **not deployed**: `api.floorwars.me` timed out from both laptops (2026-11-17, 2026-11-20), and the W4-7 deploy, pair check and exit never ran. Every Week 5 exit line needs the VM (live Grafana, a restore drill, a share card from a real session), so the Week 4 deploy is the first item of this week, not a side task.

## 0. Ground rules

- **Ionut takes every decision. You may not guess.** If this prompt, the plan, the contract, a recorded answer from Ionut or the existing code does not settle a choice, stop that item and ask Ionut with `Skill("grilling")`. Your recommendation goes with the question, and nothing uses it until Ionut answers. Look up facts yourself. Carry on with items that do not depend on the answer.
- **This prompt follows `IMPLEMENTATION_PLAN.md` and `contracts/openapi.yaml`.** If you find a difference between them, stop that item and ask Ionut. An answer that changes the plan goes into the plan in the same PR (docs rule, plan 9.3).
- **Read only the docs in section 2.** Do not read Cristea's app code beyond the lines section 2 names, and do not read the plan for Week 6. If you need something outside the list, say which file and why before opening it.
- Load `token-saver` first, then `backend-conventions`. Targeted search before reading; files over 300 lines in ranges only; never print full logs or test output (`-q`, `tail`, `grep`).
- **Contract first.** Change `contracts/openapi.yaml` only in the lead's contract commit (W5-0), as a PR that Cristea reviews, and regenerate `app/src/api/schema.ts` with `npm run generate:api` in `app/` in the same commit. Cristea's remote check-in contract change is his PR; Ionut reviews it (section 1). A server answer that differs from the contract is a bug in the server.
- **Do not break the app.** Every field name, status code and enum value the app reads is fixed by the contract. New fields are additive; nothing the app reads today is renamed or removed.
- **No new dependency, container image, CI action or external service without Ionut's approval.** Name each candidate with its licence and last release date, looked up on the day (not recalled), and wait. Section 1 lists the ones this week's plan implies; W5-0 asks for them in one question.
- Data minimisation (plan 8): no user id, e-mail or coordinates in any event, log line, metric label or response that is not the caller's own data. Metrics are aggregates; no per-user label.
- Branch per task, push it, one PR per branch into `main`; no direct push to `main`; merge commits, not squash; no Co-Authored-By or any other trailer. The lead merges after CI is green and its own checks pass.
- **VM, Azure, DNS, Discord and secret actions are Ionut's only** (deploy, migrations on the VM, secrets, NSG, ufw, storage accounts, webhooks). A session writes the steps; Ionut runs them.
- Before you claim any item done, run its verification command and paste the summary line into your report. No claim without output. If a root cause is unclear for a failing test, find it first, then fix.

## 1. Current state (checked 2026-11-28, `main` at `8a58995`)

- **Week 4 server: merged, not deployed.** On `main`: `GET /seasons`, `/me/segments`, `/me/season-stats` (landmarks, scan points), `/me/events`, `WS /ws`, `POST /landing-scans`, anti-cheat v2 flags (`device_burst`, `device_shared`, `identical_segment`, `impossible_sequence`), `tools/e2e` extended. Contract 0.9.0-draft. Migrations up to `0006_landing_scan`. The README row "Backend, week 4" still says "In progress (2026-11-20) … not merged or deployed" (stale on "merged").
- **VM:** last known deploy `fbe9c18` (2026-11-08, Week 3). Unreachable from both team PCs since 2026-11-17 (TCP connect to 443 times out, DNS resolves). Cause unchecked. Runbook section 14 holds the Week 4 deploy steps.
- **W4-7 left over:** deploy; `tools/e2e/e2e_check.py` on the VM; one bad-token WS connect through Caddy on the VM answers 401; landing stickers printed (`tools/qr/make_entrance_qr.py --landing`); the two-phone pair check (9.3, Week 4) and the Week 4 exit with Cristea; `Ionut/week4_summary.md`.
- **Week 4 notes that land in Week 5** (from `Ionut/week4_review_findings.md`, `Ionut/week4_docs_facts.md`):
  - Feed commit-order gap: `events_after` can miss an id committed after a higher one (millisecond window); fix with an `xid8` column on `game_event` and a `pg_snapshot_xmin` filter (decided 2026-11-20).
  - `game_event` rows are kept until the Week 5 retention job drops rows older than season end + 30 days (decided 2026-11-20).
  - A `season_state` writer must store `paused` (bool) and `ends_at` (ISO) in `game_event.payload`, set `season_id`, and publish with `season_id`; otherwise `event_json` raises and `/me/events` answers 500.
  - The GDPR export must include `landing_scan`. A check-in cleanup must handle `landing_scan.checkin_id`.
  - Finding 5 (later): `0006` downgrade leaves scan effects in `team_building_score`, `building_claim`, `game_event`; docstring and runbook note.
- **Contract paths for this week that exist but are not built:** `getClassifierConfig` (`GET /config`, `ClassifierConfig` with eight **inferred** threshold names), `exportMyData` (`GET /me/export`, shape "to be agreed", `additionalProperties: true`), `deleteMe` (`DELETE /me`, 204, "foreign keys cascade").
- **Contract gaps for Cristea's Week 5 screens** (plan 10, Week 5, Cristea):
  - Season results screen: no path returns a closed season's results.
  - "Season paused" banner: `Season` has `id`, `starts_at`, `ends_at` only; the app can learn `paused` only from a `season_state` socket event, so a cold start cannot show the banner.
  - Export and delete: the export shape is undefined; what `DELETE /me` does to team scores is unstated.
  - `ClassifierConfig` field names are inferred; Cristea's tuning pass 2 moves the thresholds into a structure that `GET /config` overrides (plan 9.3, Weeks 5 and 6), so the names must match his.
- **Cristea's remote check-in (decided 2026-11-25, `cristea/week_5/remote_checkin.md`):** new check-in method `pick`, check-ins last 24 h (`checkin_ttl_s` 86400), 24 h building-switch cooldown (403 `building-locked`), migration widening `ck_checkin_method`, and **removal of `impossible_sequence`** (`rules.py`, `segments/repository.py`, `service.py`, `test_anticheat.py`, `server/README.md`). Branch `feat/remote-checkin`, not created yet. Contract change reviewed by Ionut. It touches files this week's agents also touch (`config.py`, `db/models.py`, the next migration number). OPEN who builds its server half (launch question 1).
- **What exists that this week builds on (reuse, do not duplicate):**
  - `server/app/main.py`: `/metrics` is a stub (`METRICS_STUB`), "until Week 5".
  - `server/app/segments/partitions.py`: `ensure_partitions(conn)` and a CLI `main()`, run by hand on deploy today.
  - `server/app/segments/repository.py`: `purge_rejected(db, now)` (rejected receipts and resolved flags older than 30 days, unresolved flags older than 365 days), not scheduled.
  - `server/app/db/models.py`: eight `ForeignKey("user.id", ondelete="CASCADE")`; `fraud_flag` with `resolved_at` and a partial index on unresolved rows; `Season` without `paused`; no admin role anywhere.
  - `server/app/leaderboards.py`: `publish_flip`, `EVENTS_CHANNEL`, `rebuild`, `POINTS_SOURCE`; `server/app/events/feed.py`: `event_json`, `events_after`.
  - `infra/caddy/Caddyfile`: a commented admin block (`{$ADMIN_DOMAIN}`, `remote_ip` team IPs, `reverse_proxy admin:8000`) and a Grafana block with `basic_auth`; a TODO saying per-IP limits need the `caddy-ratelimit` module through `xcaddy` (the stock `caddy:2` image has none).
  - `infra/docker-compose.yml`: `caddy`, `api` (2 replicas), `migrate`, `postgres` (`postgis/postgis:18-3.6`), `valkey` (`valkey/valkey:8`). `infra/deploy.sh` with a rollback mode.
  - `docs/runbook.md` sections 1 to 14; `docs/evaluation.md`.
- **VM size: B2als_v2, 2 vCPU, 4 GiB RAM**, 32 GiB data disk (README decisions 2026-10-25). Prometheus, Grafana, Loki, Alloy, Alertmanager, three exporters and a Celery worker next to 2 API replicas, Postgres and Valkey may not fit. W5-0 measures it (Ionut, `docker stats`); where monitoring runs is launch question 5.
- **Dependencies and images the plan implies (none installed, all need approval, W5-0 looks up licence and last release):** `sqladmin` (and `itsdangerous` for its session, if not already a transitive dependency), `celery`, `prometheus-client` (or an instrumentator), images for Prometheus, Grafana, Loki, Alloy, Alertmanager, node_exporter, cAdvisor, postgres_exporter, pgBackRest, a custom Caddy build with `caddy-ratelimit`, the Trivy GitHub Action, `k6` (local tool).
- **Not this week (Week 6), do not drift into them:** the pilot, its recruiting, the final evaluation numbers, the demo script, raids, achievements, iOS.

## 2. Documents to read (and only these)

| Doc | Which part | Needed for |
|---|---|---|
| `IMPLEMENTATION_PLAN.md` | Section 10, "Week 5" (Ionut, Cristea and exit lines) | All |
| `IMPLEMENTATION_PLAN.md` | 7.1, 7.4, 7.5, 7.6, 7.7, 7.8, 7.11 | W5-5 to W5-8 |
| `IMPLEMENTATION_PLAN.md` | Sections 2 (game rules), 5 (data model), 8 (security and privacy), 7.2.1 | W5-1 to W5-4 |
| `IMPLEMENTATION_PLAN.md` | 9.2, 9.3 (Weeks 5 and 6 row), 3.3 (threshold table) | W5-2, W5-11 |
| `contracts/openapi.yaml` | `/config`, `/me/export`, `/me`, `/seasons*`, `ClassifierConfig`, `Season`, `SeasonStateEvent`, `Problem`, the shared responses | W5-0 to W5-4 |
| `cristea/week_5/remote_checkin.md` | Whole file | W5-0, review of Cristea's PR |
| `Ionut/week4_docs_facts.md`, `Ionut/week4_review_findings.md` | Whole files | W5-0, W5-3, W5-4 |
| `server/README.md` | Sections on auth, segments, leaderboards, events, WebSocket | All |
| `docs/runbook.md` | Sections 7 to 14 | W5-0, W5-7, W5-11 |
| `infra/docker-compose.yml`, `infra/caddy/Caddyfile`, `infra/deploy.sh` | Whole files | W5-1, W5-5 to W5-7 |
| `.github/workflows/server.yml` | Whole file | All (CI must stay green), W5-5 |
| Code | The files named in section 1 under "What exists", only the lines you need | All |

## 3. Checklist

### Plan coverage

| Plan line (section 10, Week 5; 9.3) | Item |
|---|---|
| Finish Week 4: deploy, e2e on the VM, stickers, pair check, exit | W5-0, W5-11 |
| Admin panel (SQLAdmin, IP-allowlisted through Caddy `remote_ip`, admin JWT role): footprints (GeoJSON), seasons, teams, fraud flags, "season paused" switch | W5-1 |
| Versioned classifier-threshold `config` table and `GET /v1/config` | W5-2 |
| Season close transaction with results snapshot; Celery jobs: rollover, partitions, digests | W5-3 |
| Retention job: partitions older than 12 months, `purge_rejected`; plus `game_event` retention and the `xid8` feed fix (Week 4 decisions) | W5-3 |
| `GET /v1/me/export` and `DELETE /v1/me` (cascade) | W5-4 |
| Caddy rate limits; security review: CORS, validation bounds, secrets, dependency scan, Trivy gate | W5-5 |
| Monitoring: Prometheus, Grafana, Loki + Alloy, Alertmanager to Discord, the 7.8 custom metrics, one demo dashboard | W5-6 |
| pgBackRest off-site and one restore drill; `deploy.sh rollback` rehearsal; `docs/runbook.md` | W5-7 |
| k6 load test on `POST /v1/segments` and the WebSocket | W5-8 |
| Battery measurement runs (moved from Cristea) | W5-9 |
| Review of Cristea's remote check-in contract and server change | W5-0 (contract), W5-10 |
| 9.3, Weeks 5 and 6: new thresholds live through `GET /v1/config` without a deploy | W5-2, W5-11 |
| Exit line | W5-11 |

Dependencies: W5-0 first (the deploy and the contract gate everything that runs on the VM). Then W5-1 + W5-2, W5-3, W5-4, W5-5 + W5-7, W5-6 run in parallel, one agent each in its own worktree. W5-8 after W5-6 (it reads the dashboard). W5-9 whenever Cristea's build with the service toggle exists. W5-10 after the code branches merge. W5-11 last.

### The seam (shared names, fixed; a change is a question for `w5-lead`)

```python
# server/app/seasons/state.py (owner: w5-admin) - the ONE writer of season_state events
def set_paused(db: Session, season_id: int, paused: bool, now: datetime) -> None: ...
    # updates season.paused, inserts game_event(type='season_state', season_id, payload={paused, ends_at}),
    # publishes after commit with season_id (the hub strips it). Used by the admin panel and by w5-jobs' close.

# server/app/seasons/close.py (owner: w5-jobs)
def close_season(db: Session, season_id: int, now: datetime) -> bool: ...
    # one transaction: lock, snapshot results into season_result, mark closed; idempotent (False if already closed)

# server/app/config_store.py (owner: w5-admin)
def current_config(db: Session) -> ClassifierConfigOut: ...  # newest active version; GET /config and the admin panel read it

# server/app/me/gdpr.py (owner: w5-gdpr)
def export_user(db: Session, user_id: uuid.UUID) -> dict[str, object]: ...
def delete_user(db: Session, valkey: Valkey, user_id: uuid.UUID, now: datetime) -> None: ...

# server/app/metrics.py (owner: w5-ops-monitor) - the ONE registry; other modules call its counters, never create their own
```

Rules for the seam:

- Only `set_paused` writes a `season_state` event, so the payload always has `paused`, `ends_at` and `season_id` (Week 4 fact).
- Migrations: one per branch. The lead assigns the order at W5-0 (`0007` …); a branch that merges later rebases and sets its `down_revision` to the head on `main`. `alembic heads` must show one head after every merge. Cristea's remote check-in migration is in the same chain.
- Metric names follow Prometheus conventions (`floorwars_` prefix, `_total` for counters, base units); no label holds a user id, e-mail, device id or token.

### 3.1 Subagents and worktrees

Same model as Week 4 (Ionut, 2026-11-19; OPEN for Week 5, launch question 9): this session (`w5-lead`) coordinates, writes the agent files, commits the contract, starts the agents, puts their questions to Ionut, re-runs every check, merges, and does W5-0, W5-9 (steps only), W5-10 and W5-11 itself. Agents may message each other about the seam; file ownership stays exclusive.

| Agent | Items | Worktree, branch | Model, effort | Owns (one owner per file) |
|---|---|---|---|---|
| `w5-lead` (this session) | W5-0, W5-10, W5-11, merges | main checkout; `contract/w5-server`, `docs/w5-ionut-prompt` | Opus, high | `contracts/openapi.yaml`, `app/src/api/schema.ts`, `server/app/api/v1/__init__.py` merge conflicts, migration order |
| `w5-admin` | W5-1, W5-2 | `<root>-w5/admin`, `feat/w5-admin` | opus, high | `server/app/admin/*`, `server/app/seasons/state.py`, `server/app/config_store.py`, `server/app/api/v1/config.py`, its migration, the `admin` service in compose and the admin block of the Caddyfile, `server/tests/admin/*` |
| `w5-jobs` | W5-3 | `<root>-w5/jobs`, `feat/w5-jobs` | opus, high | `server/app/seasons/close.py`, `server/app/jobs/*`, `server/app/events/feed.py` (xid8 lines), `server/app/api/v1/seasons.py` (results route), its migration, the `worker` service in compose, `server/tests/jobs/*` |
| `w5-gdpr` | W5-4 | `<root>-w5/gdpr`, `feat/w5-gdpr` | opus, high | `server/app/me/gdpr.py`, `server/app/api/v1/me.py` (export and delete routes only), `server/tests/me/test_gdpr.py` |
| `w5-ops-sec` | W5-5, W5-7 | `<root>-w5/ops-sec`, `feat/w5-ops-security` | sonnet, high | `infra/caddy/*` (except the admin and Grafana blocks), `infra/deploy.sh`, `infra/backup/*`, `.github/workflows/server.yml`, `.github/dependabot.yml`, `server/app/main.py` (middleware lines) |
| `w5-ops-monitor` | W5-6, W5-8 | `<root>-w5/monitor`, `feat/w5-monitoring` | sonnet, medium | `server/app/metrics.py`, `server/app/main.py` (`/metrics` route only), `infra/monitoring/*`, the monitoring services in compose, the Grafana block of the Caddyfile, `tools/k6/*` |
| `w5-docs` | docs for every item | `<root>-w5/docs`, `docs/w5-server-status` | sonnet, low | `README.md`, `server/README.md`, `IMPLEMENTATION_PLAN.md`, `docs/*` (runbook, evaluation, privacy) |

`<root>` is `C:/Users/Ionut/Desktop/sem1_an4/msa/FloorWars`. W5-10 uses the three existing reviewer agents.

Shared files (additive edits only, each agent adds its own lines and touches no one else's; the later branch in the merge order rebases and resolves):

- `infra/docker-compose.yml`: admin (`admin` service), jobs (`worker`), monitor (monitoring services).
- `server/app/db/models.py`: admin (`user.is_admin`, `season.paused`, `ClassifierConfig`), jobs (`SeasonResult`, `season.closed_at`, `game_event.txid`), Cristea's remote check-in (`CHECKIN_METHODS` and its constraint).
- `server/app/config.py`: admin (session secret, team IPs if not Caddy-only), jobs (Celery broker index), Cristea's remote check-in (`checkin_ttl_s`, `building_switch_cooldown_s`).
- `server/pyproject.toml`, `server/uv.lock`: nobody; the lead's dependency commit in W5-0 holds them all. An agent that finds it needs another dependency lists it under Blocked.

Order:

1. This session does W5-0: launch questions, baseline, the Week 4 deploy steps for Ionut, the contract commit, the six agent files (and removes the five `w4-*` agent files, launch question 9).
2. Restart the session so the agents load.
3. Create the worktrees from `contract/w5-server`, start the agents.
4. W5-10 after the code branches merge; W5-11 last.

Rules for this session: as in Week 4 (start each agent with its item IDs, worktree path and the absolute path of this prompt; re-run every verify yourself and break each guarded rule once; ask Ionut with `Skill("grilling")` for every Blocked question; each agent uses its own Postgres and Valkey containers on its own ports and stops them when done). Merge order: admin, jobs, gdpr, ops-sec, monitor, docs, and Cristea's `feat/remote-checkin` wherever Ionut places it (launch question 1).

Commands:

```
git worktree add <root>-w5/admin   -b feat/w5-admin          contract/w5-server
git worktree add <root>-w5/jobs    -b feat/w5-jobs           contract/w5-server
git worktree add <root>-w5/gdpr    -b feat/w5-gdpr           contract/w5-server
git worktree add <root>-w5/ops-sec -b feat/w5-ops-security   contract/w5-server
git worktree add <root>-w5/monitor -b feat/w5-monitoring     contract/w5-server
git worktree add <root>-w5/docs    -b docs/w5-server-status  contract/w5-server
# for each worktree:
mkdir -p <worktree>/.claude && cp -r <root>/.claude/skills <root>/.claude/agents <worktree>/.claude/
```

### Verify commands (used by every item)

As in Week 4, through the repo venv (`PY` is `C:/Users/Ionut/Desktop/sem1_an4/msa/FloorWars/.venv/Scripts/python.exe`), from `server/`, with the agent's Postgres and Valkey up:

```
$PY -m ruff check . && $PY -m ruff format --check .
$PY -m mypy app
$PY -m pytest -q
$PY -m alembic upgrade head && $PY -m alembic check && $PY -m pytest -q ../tools/qr ../tools/seed
```

Infra items also run `docker compose -f infra/docker-compose.yml -f infra/compose.local.yml config -q` and, where they add a service, bring the local stack up once. Contract-shape tests reuse `server/tests/me/contract.py`.

### W5-0 Preflight, Week 4 deploy and contract (first, lead)

- [ ] `git status`, `git branch --show-current`; `main` level with `origin/main`. List local changes; do not touch them.
- [ ] Baseline on `main`: the verify commands plus `cd app && npx jest __tests__/apiContract`. Record the summary lines.
- [ ] Ask Ionut the launch questions (section 4) with `Skill("grilling")`, one at a time, recommendation first.
- [ ] Ionut, on his PC: `curl.exe -i https://api.floorwars.me/healthz`. On a timeout, Ionut checks (Azure portal, Ionut only) that the VM runs, the NSG allows 443 from anywhere, ufw allows 443, and Caddy is up. Record the cause of the 2026-11-17/20 timeouts.
- [ ] Ionut, on the VM: the deployed commit, and `docker stats --no-stream` plus `free -m` (memory headroom for launch question 5).
- [ ] Week 4 deploy (Ionut, runbook section 14): backup, pull, migrations to `0006`, partition CLI, both replicas together, then `/healthz` 200; `/v1/seasons`, `/v1/me/events`, `POST /v1/landing-scans` 401 without a token; a bad-token WS through Caddy 401; `tools/e2e/e2e_check.py --upload` once against the VM. Write surprises in section 4.
- [ ] Contract commit on `contract/w5-server`, version `0.10.0-draft` with a changelog line, `schema.ts` regenerated, Cristea reviews. Contents per launch question 2 (recommendations below, nothing used until Ionut answers):
  - `Season` gains `paused` (boolean, **optional** in 0.10.0, "missing means false"), so `GET /seasons/active` and `GET /seasons` show it after a cold start. Optional because the column arrives with W5-1 after this commit, and `app/__tests__/contract/samples.ts` types a `Season` sample that a required field would break; it becomes required in a later contract version once deployed.
  - `GET /seasons/{id}/results` (`getSeasonResults`): 200 `SeasonResults` (`season_id`, `closed_at`, `teams`: `team_id`, `code`, `points`, `buildings_owned`, `rank`; `buildings`: `building_id`, `owner_team_id` or null), 404 when the season is unknown or not closed yet, 401.
  - `GET /me/export`: a named schema `MyDataExport` replacing "to be agreed" (sections: `user`, `devices`, `memberships`, `checkins`, `segments`, `landing_scans`, `fraud_flags`, `exported_at`; tokens and OTP hashes never exported).
  - `DELETE /me`: description of what happens to team scores (launch question 6); 204 and 401 stay.
  - `ClassifierConfig`: field names as Cristea's pass-2 structure names them (asked through Ionut); no longer "Inferred".
  - Version bump coordinated with Cristea's remote check-in PR: whichever merges second takes the next minor.
- [ ] Dependency commit on `contract/w5-server`, after launch question 12: every approved Python dependency (`sqladmin`, `celery`, `prometheus-client`, …) added to `server/pyproject.toml` and `server/uv.lock` in one commit, before the worktrees exist, so no agent edits the lockfile. `uv` is not installed on this PC: regenerate the lock the way `1c7c3df` (jsonschema) did, and CI's `uv sync --frozen` must pass.
- [ ] Write the six agent files of section 3.1 (frontmatter `name`, `description`, `tools`, `model`; body: items, worktree, branch, owned files, "read `<root>/Ionut/prompt_week5.md` by absolute path, sections 0, 1, 2, your items, the seam and section 4", verify commands, "you cannot ask Ionut: list questions under Blocked with your recommendation and carry on"). Restart; create the worktrees.
- Verify: `cd app && npm run generate:api && npx jest __tests__/apiContract` on `contract/w5-server`, and the server verify commands.
- Done when: the baseline is recorded, the launch questions are answered, the VM answers and runs `main` (or the cause is written down and Ionut has decided how to go on), the contract commit passes, and the worktrees and agents exist.

### W5-1 Admin panel and the pause switch (`w5-admin`)

- [ ] Admin identity. OPEN (launch question 3). Recommendation: a `user.is_admin` boolean (migration, default false, set by Ionut with one SQL line on the VM, never through the API). The panel's SQLAdmin `AuthenticationBackend` signs in with the existing e-mail code flow (e-mail, then code; the same OTP rate limits), accepts only `is_admin` users, and keeps a signed session cookie (`Secure`, `HttpOnly`, `SameSite=Strict`, 30 minutes). The API's access token gains no claim this week, because no API route is admin-only. Plan 7.1/8 "admin role in the JWT" is reworded to "admin flag on the user" if Ionut agrees.
- [ ] Network: a separate `admin` service (same image, its own ASGI app with only SQLAdmin, `admin:8000` as in the Caddyfile comment), behind Caddy `remote_ip` with the team IPs (Ionut supplies them as a secret or env, not committed). Everything else answers 403. The public API image does not mount `/admin`. A test asserts the public app has no `/admin` route.
- [ ] Views: buildings (name, footprint as GeoJSON polygon, validated: closed ring, SRID 4326, inside a sane bounding box; a bad polygon is refused with a message, never a 500), seasons (create, edit `starts_at`/`ends_at`; overlapping active seasons refused), teams (create, colour `#RRGGBB`), team memberships (assign or move a user within a season), fraud flags (list unresolved first, filter by rule, resolve with a note; `resolved_at` set once), classifier config (W5-2). Users are read-only (e-mail, created, flags count); no delete from the panel (that is `DELETE /me`).
- [ ] Pause switch: a season action that calls `set_paused` (seam). OPEN what a pause does to play (launch question 4). Recommendation: while paused, segment uploads are stored as `rejected` with `season_inactive` (an existing reason, no contract change), landing scans answer 403 `season-inactive`, joins and check-ins still work, ownership freezes. A test checks the `season_state` event payload, its publish with `season_id`, and that `/me/events` serialises it.
- [ ] Audit: every write in the panel logs one JSON line (admin e-mail hash as in the auth logs, table, row id, action); no values of personal fields.
- [ ] Tests: login refused for a non-admin and for a wrong code; cookie flags; each view's validation (bad polygon, overlapping season, bad colour); resolve a flag; pause and unpause write one event each; paused season rejects a segment with `season_inactive` and a scan with 403.
- Verify: the verify commands, and the local stack once: `/admin` from an allowed IP works, from another IP 403 (simulate with the Caddy matcher on the local stack).
- Done when: the tests pass, they fail if the `is_admin` check is removed (break once, check, revert), and an admin creates a season and a building on the local stack without SQL.

### W5-2 Classifier config table and `GET /v1/config` (`w5-admin`)

- [ ] Table `classifier_config` (migration): `version` (text, unique, e.g. `rules-2`), `thresholds` (JSONB), `active` (bool, at most one active row: partial unique index), `created_at`, `created_by_hash`. Seeded with the plan 3.3 values as `rules-1`.
- [ ] `GET /v1/config` (`getClassifierConfig`): the active row, `ClassifierConfig` shape, 401 without a token. `Cache-Control: max-age=300`. Field names from the W5-0 contract (Cristea's names).
- [ ] Admin view: create a new version from the active one, edit numbers (each bounded: positive, min below max, within the plan's physical ranges), activate it; the old row stays for rollback ("revert thresholds in seconds without a deploy").
- [ ] The server's own plausibility checks (`segments/rules.py`) do **not** read this table this week. OPEN (launch question 7). Recommendation: keep server bounds as code constants; the table steers the phone classifier only, because a wrong admin edit would otherwise reject honest climbs server-side.
- [ ] Tests: shape against the contract, one active row enforced by the database, activation switches atomically, bounds refused, 401.
- Verify: the verify commands. Done when: the tests pass and the 9.3 row "new thresholds live through `GET /v1/config` without a deploy" is shown on the local stack (activate a version, the next GET returns it).

### W5-3 Season close, Celery jobs and retention (`w5-jobs`)

- [ ] Celery (approval, launch question 8): broker and result backend Valkey (database index separate from the boards), one `worker` service running beat in the same process (`-B`, concurrency 1) with a memory limit. Recommendation for the 4 GiB VM; OPEN alternative: no Celery, a cron-style loop container calling the same functions.
- [ ] Season close (`close_season`, seam): when `ends_at` passes, one transaction under the season and building locks: snapshot each team's points, buildings owned and rank into `season_result` (migration), the final owner of each building, mark the season `closed_at`; idempotent; a `season_state` event is not written on close (the season simply ends; OPEN if Cristea's results screen wants one). Read through `GET /seasons/{id}/results` (contract W5-0). Leaderboard boards of a closed season are frozen (no further writes; the snapshot is the source of truth).
- [ ] Rollover: OPEN (launch question 8). Recommendation: the job only closes ended seasons; the next season is created by an admin (W5-1) and starts at its own `starts_at`; no automatic new season.
- [ ] Partitions: a daily job runs `ensure_partitions` (no second copy); the manual CLI stays for deploys.
- [ ] Retention: a daily job drops `climb_segment` partitions older than 12 months (plan 8), calls `purge_rejected`, and deletes `game_event` rows of seasons that ended more than 30 days ago (Week 4 decision). Each job logs counts only.
- [ ] Feed fix (Week 4 decision): `game_event.txid xid8 DEFAULT pg_current_xact_id()` (expand-only migration), and `events_after` returns only rows whose `txid < pg_snapshot_xmin(pg_current_snapshot())`, so an id committed after a higher one is never skipped. A test with two overlapping transactions proves it. The socket path is unchanged (it already dedupes on a set).
- [ ] Digests: OPEN (launch question 8). Recommendation: cut from Week 5 (no consent text for e-mail digests, ACS cost, no unsubscribe flow); the plan line is updated.
- [ ] Tests: close is idempotent and correct with ties; results 404 before close; partitions created ahead; retention drops only what is due (boundary days); `purge_rejected` scheduled; the xid8 gap test; jobs run against a real Postgres in tests (no Celery broker needed: call the task functions).
- Verify: the verify commands, and the worker once on the local stack (beat fires a test schedule).
- Done when: the tests pass and they fail if the `pg_snapshot_xmin` filter is removed (break once, check, revert).

### W5-4 GDPR export and delete (`w5-gdpr`)

- [ ] `GET /v1/me/export` (`exportMyData`): the caller's rows from every user-owned table, `MyDataExport` shape (W5-0), including `landing_scan` (Week 4 note) and the caller's `fraud_flag` rows (data about the user). Never exported: token hashes, OTP hashes, other users' data, receipts of other users. Rate limit OPEN; recommendation 3 per user per hour (Valkey limiter, 429 `Retry-After`).
- [ ] `DELETE /v1/me` (`deleteMe`): deletes the user; the eight `ON DELETE CASCADE` foreign keys remove owned rows. OPEN (launch question 6) what happens to team scores. Recommendation: in one transaction under the user and building locks, subtract the user's points from `team_building_score`, recompute the owners of the affected buildings (publishing any flip like a claim), remove the user from the Valkey individual boards and adjust the team boards, then delete. Reason: `leaderboards.rebuild` sums `climb_segment`, so leaving the aggregates would make a rebuild disagree with the incremental boards (the Week 3 finding 6 pattern). Refresh tokens are revoked by the cascade; an open socket of the user stays until it closes (auth on connect only) — OPEN whether to close it through the hub.
- [ ] Check every table with a `user_id` (partitioned `climb_segment` included: a cascade on a partitioned table works per partition in Postgres 18; verify with a test, do not assume).
- [ ] Logs: one line with the user id hash and row counts; the e-mail never.
- [ ] Tests: export shape against the contract and nothing of another user; delete removes every row (query each table), boards and aggregates equal a fresh rebuild afterwards, a building the user's team owned only through the user's points flips and publishes; 401; a second delete with the same token answers 401.
- Verify: the verify commands. Done when: the tests pass, and they fail if the board cleanup is removed (break once, check, revert).

### W5-5 Security pass (`w5-ops-sec`)

- [ ] Caddy per-IP limits: a custom Caddy image built with `xcaddy` and `github.com/mholt/caddy-ratelimit` (approval), pinned, built in CI and pushed to GHCR like the API image. Limits OPEN (launch question 13). Pilot players on the faculty Wi-Fi share one NAT address, so a per-IP limit counts the whole faculty as one client. Recommendation: per-IP limits only on unauthenticated paths (`/v1/auth/otp`, `/v1/auth/verify`, `/v1/auth/refresh`) at 120 per minute per IP, nothing per IP on authenticated paths (the per-user Valkey buckets already cover them); 429.
- [ ] CORS: the app is native and the admin panel is same-origin, so no CORS middleware (browsers get no `Access-Control-Allow-Origin`). A test asserts the header is absent. Recorded in plan 7.11.
- [ ] Validation bounds: a sweep of every request model for numeric and string bounds (the Week 4 bounds commit is the pattern); add what is missing, contract-additive only.
- [ ] Secrets: `git log -p` scan for keys with the approved scanner (OPEN tool; recommendation: GitHub secret scanning, already on for public repos, no new tool); the `infra/secrets/*.enc.env` stay encrypted.
- [ ] Dependency scan: `.github/dependabot.yml` for `uv`, `npm`, `github-actions`, `docker` (GitHub built-in, no new tool).
- [ ] Trivy gate: the Trivy GitHub Action (approval, pinned by commit SHA) scans the API image in `server.yml` and fails on `CRITICAL` and `HIGH` with a fix available; findings without a fix go into `.trivyignore` with a reason and a date.
- Verify: the verify commands, CI green on the branch, and the local stack once: one request over the auth limit in a minute from one IP gets a 429.
- Done when: CI is green with the Trivy step, and the rate limit is shown on the local stack.

### W5-6 Monitoring (`w5-ops-monitor`)

- [ ] `/metrics` replaces the stub with `prometheus-client` (approval). Not reachable through Caddy (internal network only; a test or a Caddy check proves `/metrics` from outside is 404). The two replicas are scraped separately.
- [ ] Custom metrics (plan 7.8): segments accepted vs rejected by reason, detection latency (`started_at` to accept, histogram), fraud flags by rule, open WebSocket connections, active users (distinct users with an upload in the last 15 minutes, computed from Valkey or SQL, not a per-user label), plus request rate, error rate and latency histograms per route template.
- [ ] Stack (placement OPEN, launch question 5): Prometheus, Alertmanager, Grafana (provisioned datasource and one dashboard JSON for the demo: golden signals per service plus the custom metrics), node_exporter, cAdvisor, postgres_exporter, Loki + Alloy for the JSON logs. Retention 7 days; memory limits on every container. Grafana behind the Caddyfile Grafana block (team IPs plus basic auth).
- [ ] Alerts (plan 7.8): API error rate above 2% for 5 minutes, p95 above 500 ms, disk above 80%, backup older than 26 hours (from W5-7's metric), certificate expiring within 14 days. To a Discord webhook that Ionut creates and stores as a secret.
- [ ] Uptime check from outside (plan 7.8): OPEN; recommendation: skip Uptime Kuma (no Raspberry Pi), use a free external HTTP monitor on `/healthz` that Ionut signs up for, or accept the gap and write it in the runbook.
- [ ] Tests: metric names and labels (no user data), counters move on an accepted and a rejected upload, `/metrics` format parses.
- Verify: the verify commands, and the local stack once: Grafana shows the dashboard with live numbers after `tools/fake_segments` uploads.
- Done when: the dashboard shows live data on the local stack and one test alert reaches a Discord test channel (Ionut's webhook).

### W5-7 Backups, restore drill, rollback rehearsal (`w5-ops-sec`, Ionut runs on the VM)

- [ ] pgBackRest (approval) as a sidecar of `postgres`: weekly full, daily differential, WAL archiving (`archive_timeout = 60s`), AES-256, two to four fulls. Target OPEN (launch question 10); recommendation: Azure Blob Storage in a second allowed EU region (pgBackRest `azure` repo type), created by Ionut.
- [ ] A metric or textfile for "age of the last good backup" for the W5-6 alert.
- [ ] Restore drill (Ionut, steps written by the agent): restore the latest backup into a throw-away container, run row-count and checksum queries on `user`, `climb_segment`, `team_building_score`, `game_event`, record the result and the time taken in the runbook ops log. RPO 5 minutes, RTO under one hour (plan 7.7).
- [ ] `deploy.sh rollback` rehearsal (Ionut): deploy `main`, roll back to the previous image, check `/healthz` and the e2e script, roll forward. Record times.
- [ ] Runbook: Week 5 deploy section (new services, secrets, migrations, the admin and Grafana domains and DNS), backup and restore, rollback, the Finding 5 downgrade note.
- Done when: the drill and the rehearsal are recorded with real times by Ionut.

### W5-8 Load test (`w5-ops-monitor`)

- [ ] k6 scripts in `tools/k6/`: batched `POST /v1/segments` with fresh `Idempotency-Key`s across many test users, and N WebSockets receiving flips. Target OPEN (launch question 10); recommendation: the local compose stack on Ionut's PC (state the machine), never the production VM while testers use it; one short low-rate smoke against the VM only with Ionut's go.
- [ ] Record in `docs/evaluation.md`: requests per second, p50/p95/p99, error rate, sockets held, the first resource to saturate (from the W5-6 dashboard), dated, with the commit.
- Done when: the numbers are recorded.

### W5-9 Battery runs (Ionut, manual)

- [ ] Needs Cristea's build with the service toggle (OPEN: does it exist? launch question 11). Per plan: drain per hour over 3 hours, service on vs off, both devices (SM-S918B, SM-G985F), same brightness and network, airplane mode off, recorded in `docs/evaluation.md` with the build commit. The lead writes the procedure; Ionut runs it and pastes the numbers.

### W5-10 Independent review (lead, read-only agents, after the code branches merge)

- [ ] `claim-transaction-reviewer` (season close, delete under locks, pause), `privacy-security-reviewer` (admin auth and network, export contents, delete completeness, metrics labels, Caddy limits, secrets), `contract-guardian` (contract 0.10.0 against the server and `schema.ts`). Also Ionut's review of Cristea's `feat/remote-checkin` server half and contract, with `claim-transaction-reviewer` on the cooldown query.
- [ ] Findings ranked, with file, line, failure scenario and fix, in `Ionut/week5_review_findings.md` (local); Ionut marks each.

### W5-11 Deploy and exit (lead with Ionut, last)

- [ ] Integration branch with all code branches merged locally; the verify commands; `alembic heads` shows one head.
- [ ] Deploy (Ionut, runbook Week 5 section), then the e2e script, `GET /v1/config`, `GET /seasons/{id}/results` 404 for the active season, export and delete on a test user.
- [ ] **Exit:** an admin creates a season and a building from the panel without SQL (Ionut); Grafana shows live metrics from the VM; a share card exports from a real session (Cristea's, needs the deployed server); the restore drill recorded (W5-7).
- [ ] 9.3 Weeks 5 and 6: Cristea's app picks up a new threshold version through `GET /v1/config` without a deploy.
- [ ] Docs (`w5-docs`, lead checks): README "Backend, week 4" (deployed) and "Backend, week 5" rows and dated decisions; `server/README.md` for every new path, job and limit; plan sections 7.x, 8 and 10 for anything that changed; the retention periods for Cristea's privacy notice in one place (`docs/privacy.md` or the plan). Write `Ionut/week5_summary.md`.
- Done when: each PR's CI is green, the deploy is verified, and every exit line is done or listed with what blocks it.

## 4. Report format

After each item, one line: `W5-n done | verify: <command> → <summary line> | commit: <sha>`. Agents post the same line; the lead copies it here after re-running the verify. Keep these sections up to date:

- **Launch questions (W5-0, asked before any agent starts):**
  1. Remote check-in server half (`pick`, 24 h, cooldown, migration, `impossible_sequence` removal): Cristea builds it on `feat/remote-checkin` and Ionut reviews, or a `w5-*` agent builds it? Recommendation: Cristea builds it as his spec says; it merges before `feat/w5-admin` so its migration is `0007` and the others follow.
  2. Contract 0.10.0 contents (W5-0 list: `Season.paused`, `GET /seasons/{id}/results`, `MyDataExport`, delete semantics, `ClassifierConfig` names from Cristea). Recommendation: all five, in one commit, Cristea reviews.
  3. Admin identity: `user.is_admin` plus e-mail-code login and a session cookie, no JWT claim (W5-1). Recommendation as written.
  4. What a pause does (W5-1). Recommendation: uploads rejected `season_inactive`, scans 403, joins and check-ins allowed.
  5. Where monitoring runs, after the W5-0 memory numbers. Recommendation: on the VM with memory limits and 7-day retention if at least 1.5 GiB is free with the current stack; otherwise Prometheus, Alertmanager and exporters on the VM and Grafana + Loki on Ionut's PC for the demo only.
  6. `DELETE /me` and team scores (W5-4). Recommendation: subtract and recompute in the same transaction.
  7. Server plausibility bounds stay code constants; `GET /config` steers only the phone (W5-2). Recommendation: yes.
  8. Celery approved (worker with beat, concurrency 1); rollover = close only; digests cut from Week 5 (W5-3). Recommendation: as written.
  9. Execution model: as Week 4 (lead plus six `w5-*` agents in worktrees), and the five `w4-*` agent files deleted. Recommendation: yes.
  10. Backup target (Azure Blob, second EU region) and load-test target (local stack). Recommendation: as written.
  11. Battery runs: does Cristea's build with the service toggle exist, and when are the phones free?
  12. The dependency and image list of section 1, looked up on the day (licence, last release). The approved Python ones go in the lead's dependency commit.
  13. Caddy per-IP limits with the faculty NAT in mind (W5-5). Recommendation: unauthenticated auth paths only, 120 per minute per IP.
- **Blocked:** one line each, the question and the recommendation. Expect at least: VM reachability and the Week 4 deploy; Cristea's review of contract 0.10.0 and his `ClassifierConfig` names; team IPs for the allowlist; the Discord webhook; the backup storage account; Cristea's phones for the pair check and the battery runs.
- **Decisions:** Ionut's answers only, one line each, dated, with the reason. You make no entries of your own.
- **Pair and phone checks:** the Week 4 pair check and exit, the battery runs, the 9.3 threshold check, the share card from a real session. Not claimed until done.
- **Surprises from the deploy:** field names, time zones, auth edges, memory.

## 5. Exit for Week 5 (server side)

- The Week 4 server is deployed and the Week 4 pair check and exit are done with Cristea, or listed with what blocks them.
- An admin creates a season and a building from the panel without SQL, from a team IP only; a non-admin cannot sign in.
- `GET /config`, `GET /me/export`, `DELETE /me` and the season results path answer as contract 0.10.0 says, tested and deployed.
- Season close, partitions and retention run as scheduled jobs; the feed no longer skips late-committed events.
- Grafana shows live metrics from the VM; alerts reach Discord.
- One backup restore and one rollback are proven with recorded times.
- k6 numbers and battery numbers are in `docs/evaluation.md`, or listed with what blocks them.
- Every row of "Plan coverage" is done, or listed as waiting with its reason.
