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
| Backend, week 2 | **Deployed and verified on the VM** (`api.floorwars.me`, release `d838858`) with `tools/e2e/e2e_check.py`: sign-in by e-mail code through Azure Communication Services, teams, active season, joining a season, QR check-in, token refresh with reuse detection. Contract 0.4.1-draft, 205 server tests, database roles `floorwars_app` / `floorwars_migrator`, placeholder buildings seeded. Real footprints for the two faculty buildings merged in `tools/seed` (#37). Open: the phone test with Cristea's screens |
| App, week 2 | **Code done, in review** (#38 to #41): segmenter and rules classifier in Kotlin, trace-replay harness with a confusion matrix and a CI precision gate (all 21 real traces in their expected class, `docs/evaluation.md`), sign-in by e-mail code with team choice, Keystore tokens and token refresh, check-in by entrance QR or one-shot location, client pointed at `https://api.floorwars.me/v1`. Checked by Jest, JUnit and an emulator click-through against the Prism mock. Open: the phone test against the server, step by step in `cristea/week_2/finish_week_2.md`; testers get `cristea/week_2/tester_guide.pdf` |
| CI, week 2 | `app` workflow (#38): ktlint, Android unit tests with the trace-replay gate, lint, typecheck, Jest, and a check that the generated API client matches the contract |
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
| 2026-10-31 | Staging is the same VM and the same compose project as production for now (one VM on student credit). A deploy to staging is a deploy to production; revisit before real users. Database roles: `floorwars_migrator` (DDL) and `floorwars_app` (DML only). | `docs/runbook.md` sections 11 and 12, `infra/sql/roles.sql` |
| 2026-10-31 | Sign-in e-mail goes through Azure Communication Services (approved by the professor), called with our own HMAC-signed REST client, no Azure SDK. Tests use a fake sender; local runs log only that a mail was sent. | `server/app/mail.py` |
| 2026-10-31 | The API uses a sync SQLAlchemy session with plain handlers in the thread pool; database access sits in thin repository modules so a later switch to async touches one layer. | `server/app/*/repository.py` |
| 2026-10-31 | Valkey access uses the official `valkey` client (valkey-py); rate limits are token buckets in Lua and fail closed (503) when Valkey is unavailable. | `server/app/valkey.py`, `server/app/auth/ratelimit.py` |
| 2026-10-31 | `FLOORWARS_ENV` defaults to `prod`; local runs and tests set `dev`. Production refuses to start without the database, Valkey, the JWT key and the ACS settings. | `server/app/config.py` |
| 2026-10-31 | Devices are keyed per user (`device` primary key `(user_id, id)`); a device id never moves between users. Plus-addressed e-mails are rejected so one mailbox is one account. | `server/migrations/versions/0002_auth.py` |
| 2026-10-31 | Check-ins never overlap per user (a new one ends the previous one; an exclusion constraint enforces it), and the 30 m geofence uses a GiST index on the footprint's geography. | Plan 3.2, check-in PR |
| 2026-11-02 | Segmenter: centred 8 s median on pressure, climbing when height rises at least 0.05 m/s over 4 s, pauses up to 15 s joined, segments of at least 1 m. Windows are in seconds (phones log 10 to 25 Hz); step events count up to 0.3 s late and in any order. The match flag calls `stepsScored`, so the scoring thresholds live in one place. | `app/android/.../segmenter/Segmenter.kt` |
| 2026-11-02 | Rules classifier uses the plan 3.3 thresholds, with the elevator speed lowered from above 1.0 to above 0.5 m/s: both real elevator rides measured 0.59 and 0.69 m/s. Rests on 2 rides in one lift on one phone. A rise with no steps under 5 s is a blow; steps over less than 2 m of ascent are a shake. | Plan 3.3, `docs/evaluation.md` |
| 2026-11-02 | Trace-replay gate: CI fails when STAIRS precision on the real traces drops below 0.9. With 3 real stairs traces, one false STAIRS drops it to 0.75, so any false STAIRS fails. Synthetic traces are replayed as a regression check only. | `TraceReplayTest.kt`, `.github/workflows/app.yml` |
| 2026-11-02 | App CI: the `app` workflow runs ktlint, the Android unit tests (with the gate), lint, typecheck, Jest and the generated-client check. Jest's timeout is 30 s, because a cold cache (always the case in CI) spends over 5 s on the first test of a suite. | `.github/workflows/app.yml`, `app/jest.config.js` |
| 2026-11-02 | Check-in libraries, approved by Cristea: `react-native-vision-camera` 5.2.4 with its peers `react-native-nitro-modules` 0.37.1 and `react-native-nitro-image` 0.15.2, and `@react-native-community/geolocation` 3.4.0. `react-native-vision-camera-barcode-scanner` 5.2.4 reads QR codes on Android; it was added without a separate approval, to confirm in #40. Location permission uses the built-in `PermissionsAndroid`, then one high-accuracy fix. | `app/package.json`, `app/src/checkin/deviceLibs.tsx` |
| 2026-11-02 | Tokens live in `react-native-keychain` (Android Keystore). One refresh at a time; `/auth/*` calls never trigger one; a 401 from `/auth/refresh` signs out and clears the Keychain; network errors and 5xx keep the session. Refresh-token reuse and expiry both sign out, because the server answers both with the same 401. | `app/src/api/client.ts`, `app/src/auth/` |
| 2026-11-02 | The client accepts `application/json, application/problem+json`, and the screens map errors from `Problem.type`, never from `detail` or `title`. | `app/src/api/client.ts`, `app/src/checkin/state.ts` |
| 2026-11-02 | The app reads only `exp` from an entrance QR to show "expired" without a network call, trusting the phone clock. The server checks the signature and the time window. | `app/src/checkin/qr.ts` |
| 2026-11-02 | The app talks to `https://api.floorwars.me/v1`. UI work against the Prism mock changes `API_BASE_URL` locally and never commits it. | `app/src/api/client.ts`, `contracts/prism/README.md` |
| 2026-11-02 | Testers get a release APK built on the laptop (signed with the debug key) and `cristea/week_2/tester_guide.pdf`. The VM only runs the server. The dev skip sign-in button stays for the sensor-logger friend build, which changes the 2026-10-21 row: it is removed before real users instead of when the stub went. | `cristea/week_2/finish_week_2.md`, `app/src/config/devFlags.ts` |

Starting values are ours and tunable from real data: 1 point per verified step, halving after 300 steps in an hour, at most 600 verified steps per 10 minutes per user, 20 steps per floor-equivalent.

## Repository layout

| Path | What is there |
|---|---|
| `IMPLEMENTATION_PLAN.md` | Project reference and six-week plan (source of truth) |
| `app/` | React Native app and Kotlin native module (`FloorSensors`). See `app/README.md` for setup and the release test build |
| `contracts/openapi.yaml` | API contract (OpenAPI 3.1) |
| `contracts/prism/` | How to run the Prism mock of the contract (`npm run mock:api` in the root `package.json`) |
| `cristea/` | Cristea's tasks and status per week. Week 2: `cristea/week_2/week_2_summary.md` (what was built), `finish_week_2.md` (manual steps to finish) and `tester_guide.pdf` (for testers) |
| `docs/` | Trace format and expected values (`trace_format.md`), classifier results (`evaluation.md`), test device log (`devices.md`), VM runbook (`runbook.md`), cost estimate (`cost.md`) |
| `infra/` | Docker Compose stack, Caddyfile, `deploy.sh`, encrypted secrets. See `infra/README.md` |
| `fixtures/synthetic/` | Synthetic labelled traces for week 1. Not real data |
| `tools/fake_segments/` | Script that posts fake climb segments to `POST /segments` (stairs, elevator, shake) with no phone |
| `tools/synthetic_traces/` | Seeded generator for the synthetic traces |
| `tools/validate_traces/` | Checker for trace files against `docs/trace_format.md` (checks 1 to 9) |
| `tools/seed/`, `tools/qr/` | Idempotent seed (placeholder buildings, teams, active season) and the signed entrance QR generator. See the README in each folder |

## Getting started

1. Clone the repo.
2. For the app: `cd app`, `npm install`, `npm test`, then `npm start` and `npm run android`. The full steps, including the Android SDK setup, are in `app/README.md`.
3. For the contract: `contracts/openapi.yaml`. Regenerate the client with `npm run generate:api` in `app/`.
4. For traces: `python tools/validate_traces/validate.py <dir_or_file>`. To see the classifier's confusion matrix on them: `cd app/android`, then `./gradlew test`.

## Working rules

- One branch per task, one PR into `main`. The other member reviews.
- No co-author trailers on commits.
- Don't commit APKs, keystores, `local.properties`, or real recordings that haven't been checked for personal data.
- Changes to the approved contract go through review by the other member.
- Plan changes go on the plan branch first, then into `main`.

## Open work

- Real-phone tests and real recordings: see `cristea/phone_tests.md`.
- Week 2 phone test against the server, and what Ionut provides for it (VM access, real footprints seeded, printed entrance codes): `cristea/week_2/finish_week_2.md`.
- Contract follow-ups from week 2: `accuracy_m` on the geofence check-in, the `urn:floorwars:problem:*` types, 403 examples so Prism can return them, and the `/config` elevator example (1.0 to 0.5 m/s, also in the server if it keeps a copy). `Team` has no display name yet.
- Elevator threshold: record more elevator rides, in another lift and on the SM-G985F.
- Backend and database (weeks 3 to 5): see the plan.
- Domain: DNS is done. When the VM runs again (Azure had a VM allocation outage in Sweden Central on 2026-10-29), set `DOMAIN=api.floorwars.me` in `/srv/floorwars/repo/infra/.env` and redeploy; Caddy then gets the certificate for the new name. If the VM moves to another region, update the `A` record to the new IP.
- Infra: CI deploy (GitHub runners have changing IPs, the NSG allows team IPs only), a systemd unit that re-runs `deploy.sh` after a reboot (decrypted secrets live on tmpfs), Trivy gate and Caddy rate limiting (week 5), second team-held age recipient in `.sops.yaml`.
- Auth: the stub is replaced (#39). Remove the dev skip flag before real users, add a sign-out button with the Home work, and sign release APKs with a real keystore instead of the debug key.
- CI: use `uv sync --locked` in the server workflow.
- Dependency audit: `npm ci` on the week 2 branches reports 48 npm vulnerabilities (2 high, 38 moderate, 8 low). Not yet triaged.
