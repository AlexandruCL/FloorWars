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
| App, week 2 | **Done** (#38 to #41 merged). Phone test passed 2026-11-06: e-mail sign-in, team choice, staying signed in after a restart, check-in by location, the too-far refusal, and the offline error. The entrance-QR phone tests (scan, camera permission off) moved to week 3. No written test report: segmenter and rules classifier in Kotlin, trace-replay harness with a confusion matrix and a CI precision gate (all 21 real traces in their expected class, `docs/evaluation.md`), sign-in by e-mail code with team choice, Keystore tokens and token refresh, check-in by entrance QR or one-shot location, client pointed at `https://api.floorwars.me/v1`. Checked by Jest, JUnit and an emulator click-through against the Prism mock. Steps are in `cristea/week_2/finish_week_2.md`; testers get `cristea/week_2/tester_guide.pdf` |
| Backend, week 3 | In progress (2026-11-07): segments, claims, scoring and standings (migration `0004_segments`, `POST /v1/segments`, read endpoints, leaderboards). Not yet deployed. |
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
| 2026-11-07 | Idempotency by a separate unpartitioned table `segment_receipt` with `PRIMARY KEY (device_id, id)`, inserted `ON CONFLICT DO NOTHING` in the batch transaction (`climb_segment` is partitioned, so its key is `(id, started_at)`). | Plan 5.1, 5.2 |
| 2026-11-07 | Ownership of a building is recomputed in the claim transaction from verified segments of the rolling 7 days; `team_building_score` keeps season totals. | Plan 2, 3.1 |
| 2026-11-07 | Ties: the current owner keeps the building, a flip needs strictly more points; with no owner, or an owner outside the tied top teams, the team that reached the tied total first wins. | Plan 2 |
| 2026-11-07 | Rejected segments are stored with `reject_reason`, so the history can show why. Out-of-bounds numbers are rejected per item; 422 is only for a body that is not a valid batch. | Plan 2, 5.1 |
| 2026-11-07 | Contract 0.5.0-draft: new rejection reasons `started_at_range`, `season_inactive`, `no_team`, and a required batch-level `device_id` checked against the signed-in user (403 `device-unknown`). | `contracts/openapi.yaml`, plan 2 |
| 2026-11-07 | Caddy caps request bodies at 1MB and ejects no replica. Replaces the 2026-10-22 "active checks" wording: active checks do not run on `dynamic` upstreams, and passive checks let two oversized anonymous requests eject both replicas. Refused connections are still retried on the next replica. | `infra/caddy/Caddyfile` |
| 2026-11-07 | Contract 0.6.0-draft: the caps count both sides of `started_at` (600 verified steps within 10 minutes, the 300-step points curve within 60 minutes), and `overlap` is a new rejection reason for a climb whose time range overlaps a verified climb of the same user. The 600-step cap holds in any upload order: verified steps with `started_at` less than 10 minutes apart never total more than 600. The points total can still depend on order: 300 steps each at 0, +31 and +61 min give 600 points uploaded chronologically and 750 with the middle climb uploaded last. A client can do this on purpose: with 300-step climbs every 31 minutes, uploading every other climb first averages 225 points per climb instead of about 150. Decided trade-off: an honest late upload can lose points, because climbs already verified after it count too. Not decided, open for the owners to review: an honest late upload can also be rejected as `rate_limit` with a fraud flag (300 steps each at 0, +9 and +18 min, with +9 uploaded last; the receipt makes that answer final for that device), and two phones recording one climb under different ids get `overlap` with a flag. Duplicates from the same device still succeed; a resend of a stored segment from another device is rejected as `no_checkin`. | `contracts/openapi.yaml`, plan 2 |
| 2026-11-07 | Interim, to revisit in a later week (replaces the open points of the row above). Contract 0.6.1-draft: the 300-step points curve counts per UTC clock hour, so a verified climb's points no longer depend on upload order (the deliberate-order gain is gone). Which climbs pass the 600-step cap still does: a late upload can be rejected where time order would have verified it, and that answer stays final for that device. Known limit: climbs on both sides of an hour boundary each get full points, at most 300 extra per boundary. `rate_limit` is flagged only when earlier climbs alone fill the cap, and `overlap` only when the same device recorded both climbs: an honest late upload or a second phone is rejected without a flag. Accepted until then: a client uploading newest first or under a second device id is never flagged (it still scores nothing), heavy climbing uploaded in time order is still flagged, and one phone re-sending a climb under new ids is flagged. A batch waiting more than 5 s for the user lock answers 503 with `Retry-After` (finding 9, first part); later lock waits in the batch are not limited. Items failing rules 1 to 7 skip the overlap and step-cap queries. Receipts per user (finding 15) and the rest of finding 9 stay open. | `server/app/segments`, `contracts/openapi.yaml` |

Starting values are ours and tunable from real data: 1 point per verified step, halving after 300 steps in a UTC clock hour, at most 600 verified steps per 10 minutes per user (counted on both sides of `started_at`), 20 steps per floor-equivalent.

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
- Week 3: phone tests of the entrance-QR check-in, which need the printed entrance codes from Ionut (see `cristea/week_2/finish_week_2.md`).
- Contract follow-ups from week 2: `accuracy_m` on the geofence check-in, the `urn:floorwars:problem:*` types, 403 examples so Prism can return them, and the `/config` elevator example (1.0 to 0.5 m/s, also in the server if it keeps a copy). `Team` has no display name yet.
- Elevator threshold: record more elevator rides, in another lift and on the SM-G985F.
- Backend and database (weeks 3 to 5): see the plan.
- Domain: DNS is done. When the VM runs again (Azure had a VM allocation outage in Sweden Central on 2026-10-29), set `DOMAIN=api.floorwars.me` in `/srv/floorwars/repo/infra/.env` and redeploy; Caddy then gets the certificate for the new name. If the VM moves to another region, update the `A` record to the new IP.
- Infra: CI deploy (GitHub runners have changing IPs, the NSG allows team IPs only), a systemd unit that re-runs `deploy.sh` after a reboot (decrypted secrets live on tmpfs), Trivy gate and Caddy rate limiting (week 5), second team-held age recipient in `.sops.yaml`.
- Auth: the stub is replaced (#39). Remove the dev skip flag before real users, add a sign-out button with the Home work, and sign release APKs with a real keystore instead of the debug key.
- CI: use `uv sync --locked` in the server workflow.
- Dependency audit: `npm ci` on the week 2 branches reports 48 npm vulnerabilities (2 high, 38 moderate, 8 low). Not yet triaged.
