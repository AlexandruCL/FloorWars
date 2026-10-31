# Prompt: Ionut, Week 2 (backend auth, teams, check-in, staging)

Give this to Claude Code in a session opened at the repo root `C:\Users\Ionut\Desktop\sem1_an4\msa\FloorWars`.
Set the model to **Opus 5.5** first (`/model opus`), and use **high** effort for the orchestrator.
The text between the lines is the prompt.

---

You are the lead of a small team of agents working for Ionut (Member B) on FloorWars. You coordinate, check and report. You do not write the code yourself. Ionut's Week 2 backend list is in `IMPLEMENTATION_PLAN.md` section 10 (Week 2, Ionut part). Cristea's own Week 2 work is in `cristea/week_2/week_2_prompt.md`; you do not do it, but you keep your work compatible with it.

## 0. Ground rules

- **Read only what a step names.** Do not read the rest of the plan, Cristea's app code or the Week 3 to 6 sections. If you need something outside the list, say which file and why first.
- **Contract first.** `contracts/openapi.yaml` is the agreed API. Any change to it is a PR that Cristea reviews. Do not change endpoints silently. Mark anything the plan does not define with `Inferred:` in the description, as the file already does.
- **Do not edit `app/src/api/schema.ts` by hand.** It is generated: `npm run generate:api` in `app/`.
- **Dependencies need Ionut's approval.** Name the candidates, their licence and last release, and wait for the answer. Candidates expected this week: `cryptography` (for Ed25519 signing and hashing, the plan allows libraries only for crypto primitives, section 7.9), and `qrcode` (for printable QR images). Nothing else without asking.
- **Commit after every subtask**, with small messages like `feat(auth): ...`, `feat(db): ...`, `test: ...`, `docs: ...`. **No Co-Authored-By or any other trailer.** Do not push and do not open a PR unless Ionut says so. Branches: `feat/w2-auth`, `feat/w2-checkin`, `feat/w2-teams`, `feat/w2-seed-qr`, `feat/w2-deploy`, each from `main`.
- **Never commit secrets or real data.** Generated keys live only in SOPS-encrypted `infra/secrets/*.enc.*` files and in the password manager. Never print a secret, a key or a database URL with its password in a report or in chat.
- **Do not touch the VM.** It is stopped or running for Ionut only. No SSH, no Azure commands, no deploy until step W2-7 says so, and then only with Ionut present.
- **Evidence before claims.** No item is "done" until its verification command has run and its one-line summary is in the report.
- **Failing test: find the cause first, then fix.** Do not patch around a symptom.

## 1. Current state (checked 2026-10-31)

- Week 1 is complete and deployed. Live: `https://api.floorwars.me/healthz` returns 200 with a valid certificate. The VM is B2ls_v2 in Sweden Central after an Azure allocation outage.
- `server/` has: FastAPI skeleton (`app/main.py`, `config.py`, JSON logs), SQLAlchemy models for `user`, `device`, `team`, `season`, `team_membership`, `building`, `refresh_token` (`server/app/db/models.py`), and one migration `0001_baseline`.
- **Missing, and must be built this week:** any `/v1` route (the `/v1` router is empty), auth code, the `checkin` table, OTP storage, check-in logic, seed data, QR tooling.
- Secrets: `app.enc.env` holds `postgres_password`, `valkey_password`, `database_url`, `valkey_url`. Week 2 adds `jwt_signing_key`, `qr_hmac_key`, and the mail credentials (see `infra/secrets/README.md`). `migration_database_url` is also due in Week 2 (plan 7.7).
- CI: `server` workflow runs ruff, mypy and pytest with PostGIS on pull requests, and builds the image for every push to `main`.
- Local tools: Python 3.13 venv in the repo's `.venv`, Docker Desktop, `infra/compose.local.yml` for a local stack. Use a local PostGIS container for tests, as CI does.
- The contract already has the Week 2 paths: `/auth/otp`, `/auth/verify`, `/auth/refresh`, `/teams`, `/seasons/{id}/join`, `/checkins`, and their schemas (`CheckinRequest`, `QrCheckinRequest`, `GeofenceCheckinRequest`, `Checkin`, `Problem`).

## 2. Decisions to get from Ionut before W2-1 starts

Ask these first, and wait for the answers. Give your recommendation with each.

1. **Sign-in e-mail in development.** Use **Mailpit** locally (a container that catches all mail and shows it in a web page; nothing leaves the PC), behind a small mail interface, so the production sender can be chosen later. Production sender (Azure Communication Services or an SMTP relay) waits for the professor's answer. Confirm.
2. **Real building footprints.** The plan asks for 2 real buildings, footprints only. The agents must not download map data. Ionut supplies the two polygons (drawn by hand, for example in a GeoJSON editor), or the seed uses clearly marked placeholder rectangles, which the rest of the code treats the same way. Confirm which.
3. **Check-in rule for one active check-in per user.** The data review (`server/docs/er_review.md`, item on overlapping check-ins) left this open. Recommend: a new check-in closes the previous one for that user (no overlap allowed), enforced in the same transaction, so the segment attribution in Week 3 is unambiguous.
4. **Geofence index.** Recommend a functional GiST index on `footprint::geography` for the 30 m check, so `ST_DWithin` uses the index (er_review item 12).
5. **Cristea's agreement.** Show Cristea the Week 2 auth flow and the check-in request/response before W2-1 codes against them. Cristea codes against the mock until then.

## 3. Items

Track A (auth and data): W2-0, then W2-1, then W2-2. Track B (teams, check-in): W2-3 starts after W2-1 has its migration. W2-4 and W2-5 come after Track A and B. W2-6 is the staging deploy, last.

### W2-0 Preflight (first)
- Baseline on `main`: `ruff check`, `ruff format --check`, `mypy app`, `pytest` with `FLOORWARS_TEST_DATABASE_URL` set to a local PostGIS (`postgis/postgis:18-3.6`). All must pass before anything changes.
- Check the local stack starts (`compose.local.yml`) and `/healthz` answers.
- Check `alembic upgrade head` and `alembic check` against the local database.
- Report the output lines. Do not install anything.
- Verify: all five commands pass, and the report has their summary lines.

### W2-1 Auth core (Track A, Python)
- Migration `0002_auth`: `otp_challenge` (e-mail, hashed code, `expires_at` 10 min, `attempts` with a max of 5, `consumed_at`), extra `user` columns for `terms_accepted_at` and `age_confirmed` (under 18 rejected, plan section 2), `device` registration fields (`model`, `has_barometer`, `last_seen_at`). Expand-only, no drops (plan 7.7).
- `POST /v1/auth/otp`: allow-listed university e-mail domains from settings, rate limited per e-mail and per IP with a Valkey token bucket (plan 3.4, 7.11), code hashed with a per-challenge salt, the code is never logged or returned.
- `POST /v1/auth/verify`: at most 5 attempts per challenge, constant-time comparison, a successful verify consumes the challenge, creates the user if needed, registers the device.
- Access tokens: JWT EdDSA, 15 minutes, `sub`, `exp`, `aud`, `kid` (plan 7.9). Signing key from `jwt_signing_key`, which is generated locally and stored in SOPS, never printed.
- Refresh tokens: 256-bit opaque, stored as SHA-256 hash, rotated on every use, presenting a used token revokes the whole `family_id`.
- `POST /v1/auth/refresh` as the contract describes.
- Tests: the full flow, OTP abuse (attempt 6 fails, expired code fails, wrong domain fails), token reuse revokes the family, a forged access token fails.
- Verify: `pytest -q tests/auth` passes against PostGIS, and the summary line is in the report.

### W2-2 Teams and seasons (Track A, Python)
- `GET /v1/teams` (list with `code` and `color_hex`). `POST /v1/seasons/{id}/join`: one team per user per season, enforced by the `team_membership` primary key, a second join returns 409 `Problem`.
- `GET` of the active season is needed by the app. Add it only if the contract already describes it; otherwise, Inferred and a contract PR.
- Tests: join once works, second join is rejected, unknown season is 404, team list matches seed.
- Verify: `pytest -q tests/teams` passes.

### W2-3 Check-in (Track B, Python, PostGIS)
- Migration `0003_checkin`: `checkin` table per plan 5.1 (`user_id`, `building_id`, `method` as `qr` or `geofence`, `valid_during tstzrange`), a CHECK on `method`, the overlap rule from decision 3, the functional GiST index from decision 4.
- `POST /v1/checkins` with a QR body: verify the HMAC-SHA256 signature from `qr_hmac_key` (the QR payload carries `building_id`, an issue time and a key id), reject forged, expired (outside the QR's window) and malformed tokens with `Problem`. Compare signatures in constant time.
- Geofence body: `ST_DWithin` on the geography cast, 30 m, against `building.footprint`. Outside the radius is rejected.
- Success creates the `checkin` row with a 90-minute range and returns the response from the contract, which the app shows as "Checked in: Building X, 89 min left".
- Tests: valid QR, forged QR, expired QR, geofence inside and outside 30 m, a second check-in closes the first, the index is used (`EXPLAIN` in a test, with a note on the result).
- Verify: `pytest -q tests/checkins` passes; paste the `EXPLAIN` line.

### W2-4 QR generator and seed data (Track B, Python, tools)
- `tools/qr/make_entrance_qr.py`: prints one signed QR per building as an SVG or PNG, with the building name under it. Uses `qrcode` only after approval.
- `tools/seed/seed.py`: idempotent (running twice changes nothing). Creates 2 buildings (footprints from decision 2), 4 to 5 teams with `color_hex`, one active season. It never creates users.
- Tests: running the seed twice gives the same row counts; the QR tool output decodes back to the building id with the HMAC verified.
- Verify: `pytest -q tools/qr tools/seed` passes.

### W2-5 Configuration and secrets (Track A)
- Settings for the new values in `server/app/config.py` (`FLOORWARS_ALLOWED_EMAIL_DOMAINS`, mail backend, token lifetimes). Document each in `server/.env.example` and `server/README.md`.
- Generate `jwt_signing_key` and `qr_hmac_key` locally with the `cryptography` library and random bytes, encrypt them straight into `infra/secrets/auth.enc.env` (or a `.enc.yaml` for the PEM) with SOPS, and check that the file shows only `ENC[...]` values. Never print them.
- Add `migration_database_url` handling for the least-privilege app role (plan 7.7): a documented role with DDL rights for migrations and a role with DML only for the app. Create the SQL for both; do not run it on the VM.
- Verify: `sops --decrypt` round trip matches, and `git grep` finds no plaintext key in the repo.

### W2-6 Staging deploy and exit (last, with Ionut)
- Staging is the same VM and compose project for now (plan 9.2, section 7.1). Document this as a decision in `docs/` and the README.
- Prepare the `deploy.sh` changes needed for the new secrets, and the migration step with the migration role. Open a PR. Do not run it.
- **Only when Ionut says the VM is running:** run `sudo /srv/floorwars/deploy.sh <sha>` with Ionut at the keyboard, check `/healthz`, check `/v1/auth/otp` with Mailpit or a log entry, and report.
- Exit test with Cristea's app on a real phone: sign up, pick team, scan the entrance QR, see "Checked in: Building X, 89 min left".

## 4. Agents, models and skills

Start each agent with the Agent tool. Give it the item IDs, its branch and its worktree (`isolation: "worktree"`), and the skills to load first with the Skill tool. An agent reads only the files its items name.

| Agent | Items | Model and effort | Skills to load | Why this model |
|---|---|---|---|---|
| `w2-preflight` | W2-0 | Haiku 5.5, low | none | Runs fixed commands and reports output |
| `w2-auth` | W2-1, W2-5 | **Opus 5.5, high** | `web-backend`, `backend-conventions`, `docs-sync` | Token rotation, OTP abuse and signing keys. A mistake here is a security hole |
| `w2-teams` | W2-2 | Sonnet 5.5, medium | `backend-conventions` | Clear rules, small code |
| `w2-checkin` | W2-3 | **Opus 5.5, high** | `web-backend`, `backend-conventions` | HMAC verification, geography queries, index choice |
| `w2-seed-qr` | W2-4 | Sonnet 5.5, medium | `backend-conventions` | Scripts with clear tests |
| `w2-deploy` | W2-6 (prep) | Sonnet 5.5, medium | `backend-conventions`, `docs-sync` | Scripts and documentation; the risky steps run only with Ionut |

**Reviewers** (run after each branch is committed, read-only):
- `privacy-security-reviewer` on `w2-auth`, `w2-checkin` and `w2-deploy`, model Opus 5.5 (it checks for secret leaks, token handling and data minimisation).
- `claim-transaction-reviewer` on the migrations (its scope is the schema and locking; the check-in overlap rule is the part that matters).
- `contract-guardian` on any change to `openapi.yaml`.
- `code-reviewer` on each branch, model Sonnet 5.5.

Agents do not talk to each other. You route their blockers: if an agent reports a blocked item, copy it into section 5 and carry on with the rest.

## 5. Blocked

Record here, with the item ID and the question. Do not guess.

## 6. Order and checks

1. Ask Ionut the section 2 decisions. Wait.
2. Run `w2-preflight`. Wait for its report.
3. Run `w2-auth` and `w2-teams` in parallel (different branches, different worktrees). `w2-teams` waits for the `0002` migration commit from `w2-auth` before it starts its tests.
4. Run `w2-checkin` after `w2-auth` has committed its migration (`0003` depends on the `user` table changes).
5. Run `w2-seed-qr` in parallel with `w2-checkin`.
6. Run the reviewers on each branch. Fix only findings Ionut agrees to.
7. Re-run every item's verification command yourself before you report it done. Agent reports are evidence, not proof.
8. Only when Ionut says the VM runs: `w2-deploy` prepares, then you run the deploy with Ionut.

## 7. Report format

For each item: ID, branch, commit hashes, the verification command, its summary line, open questions. Then the list of blockers from section 5. Keep it short. Do not paste file contents.

## 8. Exit for Week 2 (plan)

- The auth flow works end to end against PostGIS in CI: request code, verify, refresh, reuse detection.
- Check-in works for QR and geofence, with the forged and expired cases rejected.
- The seed and the QR tool run.
- Staging (the VM) serves the new version, with `/healthz` and `/v1/auth/otp` answering.
- On a real phone: sign up, pick team, scan the entrance QR, see "Checked in: Building X, 89 min left".

---

## After the run

- Review each branch yourself, then open PRs in this order: `feat/w2-auth`, `feat/w2-teams`, `feat/w2-checkin`, `feat/w2-seed-qr`, `feat/w2-deploy`. Cristea reviews every contract change.
- Keep the VM stopped between sessions, and start it only for the deploy and the phone test.
