# FloorWars

**Take the stairs, take the building.** A campus territory game. Every sensor-verified stair climb adds points to your faculty's claim on a real building. Phones with a barometer and a step detector do the verification, so no hardware goes into the buildings.

Team: **Cristea** (Member A) and **Ionut** (Member B). Client: React Native (bare, TypeScript), Android first. Backend: FastAPI, PostgreSQL with PostGIS, Valkey, Celery (planned, see the plan).

The full project reference and six-week plan is [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). It is the single source of truth. This README gives the overview and the decisions taken so far.

## Status

| Area | State |
|---|---|
| Week 1, code | Done: app shell, Kotlin sensor module, foreground service, sensor logger, API client and auth stub, contract, release test build |
| Week 1, synthetic data | Done: 24 labelled synthetic traces, generator, checker, trace spec |
| Week 1, real phones | Done 2026-10-29: 21 real traces in `/traces` (SM-S918B, SM-G985F, all six labels), phone checks passed, checker 20 PASS and 1 reviewed FAIL. |
| Building territory | Plan, scoring rule, floor-equivalent helper and contract 0.2.0-draft (`GET /buildings/{id}/standings`, `building_flipped`) merged and reviewed by both members |
| Backend, week 1 | Done: FastAPI skeleton (`/healthz`, `/metrics` stub, JSON logs), Alembic baseline with 7 tables (`user`, `device`, `team`, `season`, `team_membership`, `building`, `refresh_token`), server tests. API endpoints start in week 2 |
| Infra, week 1 | Done: deployed on the Azure VM `floorwars-vm` (Sweden Central, B2als_v2, hardened) with Docker Compose, Caddy and Let's Encrypt. `/healthz` answered over HTTPS at `https://api.4.223.83.29.sslip.io/healthz`. The domain `floorwars.me` is registered and `api.floorwars.me` points at the VM; the server switches to that name at its next start (see open work) |
| CI, week 1 | Done: `server` workflow (ruff, mypy, pytest with PostGIS on pull requests, multi-arch image pushed to GHCR for every commit on `main`). Deploy from CI is week 2 |
| Notifications | No Firebase (course rule, 2026-10-29). Own channel planned for week 4: `game_event` feed, WebSocket replay from the Kotlin sensing service, polling fallback, local notifications (plan 7.2.1) |
| Fakes and mock | Done: `tools/fake_segments/` and a Prism mock config (`contracts/prism/`) |

## How the game works

- **Territory is per building.** A building is the claimed object. The team with the most points in a building over the rolling 7-day window owns it.
- **Points come from verified stair steps.** A segment scores only if its step count matches its pressure change: stairs need about 4 to 8 steps per metre of ascent. Elevator rides, flat walking and shaking score nothing.
- **Floors are a display estimate.** 20 verified steps is shown as one "floor (estimate)". It is never a real storey number.
- **No building data is required.** Ascent is measured in metres from the barometer. The app does not know floor counts, heights or room positions.
- **Anti-cheat:** on-device classifier, server-side plausibility checks, per-user rate limits, signed expiring QR codes at the entrance.

## Decisions taken

Dates are when the decision was made. The rule that is in force is in the plan and in the docs linked below.

| Date | Decision | Where |
|---|---|---|
| 2026-10-21 | Bare React Native, TypeScript, Android first. Kotlin native module `FloorSensors` for sensing. | Plan section 4 |
| 2026-10-21 | Foreground service of type `health` for logging. Pressure and step detector registered at game rate. | `app/android` |
| 2026-10-21 | API contract approved by both members. Every later change is a reviewed PR. | `contracts/openapi.yaml` |
| 2026-10-21 | Week 1 can be completed on synthetic data. Synthetic traces are labelled and never counted as real. | `docs/trace_format.md`, `fixtures/synthetic/` |
| 2026-10-21 | Friend test builds use a release APK with a dev-only skip sign-in flag. The flag is removed when the real auth replaces the stub. | `app/src/config/devFlags.ts` |
| 2026-10-22 | Requirement: runs on any Android phone with a barometer. Capabilities are checked at run time. No dependency on phone model names. | `cristea/phone_tests.md` |
| 2026-10-22 | No building floor data. Ascent is measured in metres. Floors removed as a game unit. | Plan sections 2, 3, 5, 6 |
| 2026-10-22 | Territory per building. Points per verified stair step, with a pressure-steps match (the scoring rule). | Plan section 3.3 |
| 2026-10-22 | Secrets: SOPS + age files `infra/secrets/<name>.enc.<env\|json\|yaml>`, decrypted by `deploy.sh` to tmpfs and mounted as Compose secrets. API secret files carry the `floorwars_` prefix. | `infra/secrets/README.md` |
| 2026-10-22 | Caddy balances over every API replica (`dynamic a`) with active `/healthz` checks; `/metrics` is not public. | `infra/caddy/Caddyfile` |
| 2026-10-22 | Floor-equivalent for display only: 20 steps = 1 floor, labelled "floors (estimate)". | Plan section 2, `app/src/scoring/floorEquivalent.ts` |
| 2026-10-22 | Contract 0.2.0-draft for building territory: `GET /buildings/{id}/standings` replaces `/floors`, `building_flipped` replaces `floor_flipped`, steps-based stats, rejection reasons and limits. Landing scans name a building, never a floor. | `contracts/openapi.yaml` |
| 2026-10-25 | Production VM in Sweden Central (the student subscription only allows a short list of EU regions; West Europe is blocked). Size B2als_v2 (2 vCPU, 4 GiB, about $28 a month), no availability zone, separate 32 GiB encrypted data disk. | `docs/cost.md`, `docs/runbook.md` |
| 2026-10-25 | The VM pulls the repo with a read-only GitHub deploy key and pulls the public GHCR image `ghcr.io/alexandrucl/floorwars-api`. | `docs/runbook.md` |
| 2026-10-25 | CI builds an image for every commit on `main`, because `deploy.sh` pulls the image tagged with the deployed commit. Pull requests keep the path filter. | `.github/workflows/server.yml` |
| 2026-10-25 | Until the real domain is ready the API name is `api.4.223.83.29.sslip.io` (resolves to the VM, certificate from Let's Encrypt). Switching is one line in `infra/.env`. Replaced on 2026-10-29 by `api.floorwars.me`. | `infra/.env.example` |
| 2026-10-29 | The API address is `https://api.floorwars.me` (domain `floorwars.me` from the GitHub Student Pack, DNS `A api -> 4.223.83.29`, no other records). | `contracts/openapi.yaml`, `cristea/vm_guide.md` |
| 2026-10-25 | ~~Firebase project for FCM only~~ Replaced on 2026-10-29, see the next row. | |
| 2026-10-29 | No Firebase or managed push service (professor's rule). Notifications use our own channel: `game_event` table, WebSocket replay from the Kotlin sensing service, WorkManager polling fallback, local Android notifications. The FCM key and the Firebase project are deleted. | Plan section 7.2.1 |

Starting values are ours and tunable from real data: 1 point per verified step, halving after 300 steps in an hour, at most 600 verified steps per 10 minutes per user, 20 steps per floor-equivalent.

## Repository layout

| Path | What is there |
|---|---|
| `IMPLEMENTATION_PLAN.md` | Project reference and six-week plan (source of truth) |
| `app/` | React Native app and Kotlin native module (`FloorSensors`). See `app/README.md` for setup and the release test build |
| `contracts/openapi.yaml` | API contract (OpenAPI 3.1) |
| `contracts/prism/` | How to run the Prism mock of the contract (`npm run mock:api` in the root `package.json`) |
| `cristea/` | Cristea's week 1 tasks and status |
| `docs/` | Trace format and expected values (`trace_format.md`), test device log (`devices.md`), VM runbook (`runbook.md`), cost estimate (`cost.md`) |
| `infra/` | Docker Compose stack, Caddyfile, `deploy.sh`, encrypted secrets. See `infra/README.md` |
| `fixtures/synthetic/` | Synthetic labelled traces for week 1. Not real data |
| `tools/fake_segments/` | Script that posts fake climb segments to `POST /segments` (stairs, elevator, shake) with no phone |
| `tools/synthetic_traces/` | Seeded generator for the synthetic traces |
| `tools/validate_traces/` | Checker for trace files against `docs/trace_format.md` (checks 1 to 9) |

## Getting started

1. Clone the repo.
2. For the app: `cd app`, `npm install`, `npm test`, then `npm start` and `npm run android`. The full steps, including the Android SDK setup, are in `app/README.md`.
3. For the contract: `contracts/openapi.yaml`. Regenerate the client with `npm run generate:api` in `app/`.
4. For traces: `python tools/validate_traces/validate.py <dir_or_file>`.

## Working rules

- One branch per task, one PR into `main`. The other member reviews.
- No co-author trailers on commits.
- Don't commit APKs, keystores, `local.properties`, or real recordings that haven't been checked for personal data.
- Changes to the approved contract go through review by the other member.
- Plan changes go on the plan branch first, then into `main`.

## Open work

- Real-phone tests and real recordings: see `cristea/phone_tests.md`.
- Backend and database (weeks 2 to 5): see the plan. First in line for week 2: auth, check-in, a separate database role for migrations, and an async DB session before the first `/v1` route (see `server/docs/er_review.md`).
- Domain: DNS is done. When the VM runs again (Azure had a VM allocation outage in Sweden Central on 2026-10-29), set `DOMAIN=api.floorwars.me` in `/srv/floorwars/repo/infra/.env` and redeploy; Caddy then gets the certificate for the new name. If the VM moves to another region, update the `A` record to the new IP.
- Infra: CI deploy (GitHub runners have changing IPs, the NSG allows team IPs only), a systemd unit that re-runs `deploy.sh` after a reboot (decrypted secrets live on tmpfs), Trivy gate and Caddy rate limiting (week 5), second team-held age recipient in `.sops.yaml`.
- Auth: replace the stub and remove the dev skip flag (T7 follow-up). Sign release APKs with a real keystore instead of the debug key.
- CI: the app has no workflow yet. The contract test runs under `npm test` locally. Use `uv sync --locked` in the server workflow.
- Dependency audit: the app reports 54 npm vulnerabilities (5 moderate, 49 high). Not yet triaged.
