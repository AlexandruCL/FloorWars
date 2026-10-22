# Prompt: Ionut, Week 1 (backend, infra, contract)

Give this to Claude Code in a session opened at the repo root. Start in plan mode. The text between the lines is the prompt.

---

You are the lead of a small team of agents working for Ionut (Member B) on FloorWars. Your job is Ionut's Week 1 list from `IMPLEMENTATION_PLAN.md` section 10.

## Read first (targeted reads, not the whole repo)
- `IMPLEMENTATION_PLAN.md` sections 3.1, 4, 5, 6, 7.1 to 7.6, 9, 10 (Week 1)
- `README.md` (decisions and working rules)
- `cristea/week_1_implementation.md` (what exists in `main`: the app, the approved contract, the scoring helpers, the synthetic traces) and `cristea/week_1_tasks.md` (what is done)
- `Ionut/manual_steps.md` (the manual steps I do myself; do not duplicate or run them)

## Facts already established (do not redo)
- Cristea's T1 to T8 are merged. The app is React Native 0.88.0 in `app/`, Android `applicationId` is `com.floorwars`.
- `contracts/openapi.yaml` exists (OpenAPI 3.1, 18 paths) and both members approved it on 2026-10-21, then it was revised for building territory. Changes need a reviewed PR. Task 3 is an **audit**, not a rewrite. Known suspect: line ~417 still mentions `floor_flipped`; the plan says `building_flipped {building_id, from_team, to_team, at}` and `season_state {paused, ends_at}`.
- The client is generated from the contract: `npm run generate:api` in `app/` (output must stay byte-identical unless the contract changes). Contract samples live in `app/__tests__/contract/`.
- `fixtures/synthetic/` has 24 labelled synthetic traces; `python tools/validate_traces/validate.py fixtures/synthetic` passes 24/24. That satisfies "at least 20 labelled traces" for Week 1 on synthetic data (agreed in the README). Real recordings are Cristea's open work in `cristea/phone_tests.md`.
- Scoring rule: points per verified stair step only when steps and pressure agree (4 to 8 steps per metre, ascent 2.0 to 120.0 m, steps 1 to 2000). `app/android/.../classifier/StepScoring.kt` is the reference implementation. Floors are a display estimate (20 steps = 1 floor), never stored.
- `.gitignore` currently contains `.claude/` and `graphify-out/`. Project agents and skills therefore live untracked. Do not change `.gitignore` for that without asking me. Make sure `google-services.json`, `*.key`, `.env*`, `infra/secrets/*` plaintext, and `__pycache__`/`.venv` are ignored, and show me the diff of `.gitignore` before committing it.
- The environment is Windows 11 with PowerShell and Git Bash. Docker and Python availability are unknown: check with `docker --version` and `python --version` and tell me what is missing.

## Rules
- Follow my global workflow: inspect, plan, **wait for my approval of the plan**, implement, test, summarise. Your first reply is only the plan.
- One branch per task (`feat/<task>`), branched from `main`. **Commit after every task and every meaningful subtask**, small commits, message style like `git log` (`feat:`, `docs:`, `ci:`, `chore:`). No Co-Authored-By trailer on these commits (README working rule). Never push, merge or open PRs unless I say so.
- Never commit secrets: keystores, `google-services.json`, service-account keys, `.env`, age private keys, `local.properties`. Encrypted SOPS files only.
- Do not install dependencies, pull Docker images, download data, or run any cloud, account or SSH command without asking me for that specific step. Anything in `Ionut/manual_steps.md` is mine. Where code needs a value from those steps (domain, age public key, VM host), use a clearly named placeholder and list it.
- Docs rule: if you add an endpoint, table, env var or threshold, update the plan or `/contracts` in the same PR.
- Keep output short: no full logs, no big diffs in chat.

## Team of subagents
Use the Agent tool. Run independent workers in parallel, each in its own worktree (`isolation: "worktree"`) on its own branch, then integrate in the order below. Every worker loads the listed skills with the Skill tool before it starts and commits its own work.

| Worker | Task | Skills |
|---|---|---|
| server-scaffold | Task 1 and Task 4. Scaffold `/server` (`pyproject.toml`, `app/main.py`, `app/config.py`, tests) and `/infra`. FastAPI skeleton: `/healthz`, settings from env (twelve-factor), structured JSON logging, `/metrics` stub. pytest for `/healthz` | backend-conventions, docs-sync |
| db-baseline | Task 2. Review the ER model (section 5) and list issues. Then the Alembic baseline: `user`, `device`, `team`, `season` (`tstzrange` with an exclusion constraint, needs `btree_gist`), `team_membership` (composite PK), `building` (PostGIS `Polygon, 4326`, GiST, no floor columns), `refresh_token` (hash unique, family id). Test: apply all revisions to an empty Postgres/PostGIS and run `alembic check`. Starts after server-scaffold has merged the layout | backend-conventions |
| contract | Task 3 audit of `contracts/openapi.yaml` vs section 6: endpoint list, `Idempotency-Key`, `{accepted, rejected, flips}`, segment bounds and body, standings endpoint, WebSocket event schemas (`building_flipped`, `season_state`), stale `floor_*` wording. Validate with `openapi-spec-validator` if already available. Propose fixes in a branch; regenerating the app client and running its tests needs my approval | docs-sync, scoring-rules |
| ci-docker | Task 5. `.github/workflows/server.yml`: ruff, mypy, pytest with a PostGIS service container on PRs; multi-stage non-root `Dockerfile` (plan 7.3); `docker buildx` for linux/amd64 and linux/arm64; push to GHCR only on `main`, tagged by SHA. Do not touch Cristea's app workflow (there is none yet) | backend-conventions |
| infra | Task 6, code part only. `infra/docker-compose.yml` (caddy, api, postgres+PostGIS, valkey; four networks, `data` internal; only Caddy publishes ports; secrets via `/run/secrets`), `infra/caddy/Caddyfile` with a `{$DOMAIN}` placeholder, `infra/deploy.sh` with rollback skeleton, `.sops.yaml` with an age public key placeholder, `docs/cost.md` (monthly estimate), and `docs/runbook.md` with the VM hardening commands that match `Ionut/manual_steps.md` | backend-conventions, docs-sync |
| fakes | Task 7. `tools/fake_segments/` script that posts valid batches to `POST /v1/segments` with an `Idempotency-Key` (no phone), a dry-run mode, and a Prism mock config plus a short usage note for Cristea. Generated segments must satisfy the scoring rule (about 6 steps per metre, vertical speed 0.1 to 0.9 m/s). Test it against the contract samples | scoring-rules, trace-check |
| traces | Verify only: run the trace checker on `fixtures/synthetic`, report counts, change nothing | trace-check |

Integration order: server-scaffold, then db-baseline and ci-docker, then infra, then contract and fakes (fakes use the final contract), then traces check.

## Review gate
After the branches exist, spawn read-only reviewers on each diff and give me their findings (do not fix without my say-so):
- contract-guardian: contract and fakes branches
- claim-transaction-reviewer: db-baseline (schema, constraints, indexes against section 5)
- privacy-security-reviewer: infra, CI, secrets handling, `.gitignore`
- code-reviewer (global agent): server-scaffold

Finish with the `docs-sync` skill: update README "Status", "Decisions taken" (dated rows) and "Open work", and `Ionut/` notes if anything changed.

## Output
1. First reply: the plan only. A table of tasks with files to create, commands to run, branch names, dependencies and any questions that block you.
2. After I approve: implement, then give me a short summary: branches and commits, test results (with the exact commands), risks, open placeholders, and which steps in `Ionut/manual_steps.md` are now unblocked.

---

## After the run
- Review each branch yourself, then open PRs for Cristea to review (`openapi.yaml` changes need Cristea's approval).
- Do the manual steps in order from `Ionut/manual_steps.md`.
