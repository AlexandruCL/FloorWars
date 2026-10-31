# FloorWars server

FastAPI backend (plan sections 4.1, 6 and 7). Current state: `/healthz`, a stub `/metrics`,
settings, structured JSON logging, the database schema (Alembic `0001_baseline`, `0002_auth`) and
the `/v1/auth/*` sign-in endpoints (contract 0.4.0-draft).

## Code layout (for new features)

| Module | What it gives |
|---|---|
| `app/api/v1/__init__.py` | The `/v1` router. A feature adds `app/api/v1/<feature>.py` with its own `router` and lists it in `_FEATURE_ROUTERS`. |
| `app/api/deps.py` | `CurrentUser` (signed-in `User` from the Bearer access token, else 401 Problem), `DbSession` (sync SQLAlchemy session, no autocommit), `AppSettings`, `Tokens`, `Mail`, `Limiter`. |
| `app/api/problems.py` | RFC 9457 errors: raise `ProblemError(status, title, detail, type_=..., headers=..., **ext)` or `unauthorized`, `forbidden`, `not_found`, `conflict`, `too_many_requests`, `service_unavailable`; `problem_doc("...")` documents a problem response in OpenAPI (a `$ref` to the one shared `Problem` component). Validation errors are 422 problems with an `errors` list (no echoed input). |
| `app/auth/` | Sign-in: `tokens` (EdDSA JWTs), `otp`, `ratelimit` (Valkey token buckets), `repository` (all SQL), `service` (flows), `schemas`. |
| `app/constants.py` | `HOUR_S`, `DAY_S`, `OTP_MAX_ATTEMPTS` (no imports, safe for settings and models). |
| `app/mail.py` | `MailSender` with `acs`, `log` and `fake` backends. |
| `app/valkey.py` | Thin wrapper around `valkey-py` (pooled, 2 s timeouts, one retry on connection errors); every failure is `ValkeyError`, and the rate limiter fails closed on it. |

Handlers are plain `def` (FastAPI runs them in its thread pool) on the sync session; SQL lives in
small repository functions so a later move to async touches one layer.

Tests: `tests/conftest.py` has the shared fixtures `migrated` (test database at head), `clean`
(truncates every application table, flushes the test Valkey), `make_app(**settings_overrides)`
and `client` (started `TestClient`s). `tests/helpers.py` has `settings_for_tests`, `insert_user`,
`auth_headers(app, user_id)` (a valid access token), `new_email`, `sign_in` and `last_code`.
Modules can run in any order: `tests/test_migrations.py` always leaves the database at head.

## Run

From `server/`, with the project venv active (Python 3.13). `FLOORWARS_ENV` defaults to `prod`,
which needs the full configuration, so set `dev` locally:

```sh
export FLOORWARS_ENV=dev
uvicorn app.main:app --reload
curl -s localhost:8000/healthz   # {"status":"ok"}
```

## Test and lint

```sh
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m mypy app
```

Dependencies are declared in `pyproject.toml` (`dev` dependency group for test and lint tools)
and pinned in `uv.lock`. After changing dependencies run `uv lock` and commit the lockfile;
CI and the image install with `--frozen` and fail if it is stale (`uv lock --check`).

## Docker and CI

Build and run the image from the repo root (plan 7.3):

```sh
docker build -t floorwars-api:local server
docker run --rm --read-only -p 8000:8000 floorwars-api:local
curl -s localhost:8000/healthz
```

The `Dockerfile` has two stages: a builder that installs the locked, non-dev dependencies
with uv (pinned version) into `/app/.venv`, and a `python:3.13-slim` runtime that runs as
uid 10001, writes nothing to disk (bytecode is precompiled, so `read_only: true` works), and has a
`HEALTHCHECK` on `/healthz`. `.dockerignore` keeps `.venv`, tests, caches and `.env*` out of the
build context. Secrets are never baked in; they are mounted at `/run/secrets` (plan 7.5).

`.github/workflows/server.yml` runs on pull requests and on pushes to `main` that touch
`server/`, `contracts/` or the workflow itself:

- `lint-test`: `uv sync --frozen`, OpenAPI validation of `contracts/openapi.yaml`,
  `ruff check`, `ruff format --check`, `mypy app` and `pytest -q`. `postgis/postgis:18-3.6` and
  `valkey/valkey:8` service containers are started and `FLOORWARS_TEST_DATABASE_URL` and
  `FLOORWARS_TEST_VALKEY_URL` are set, so database, migration and auth tests run in CI (they are
  skipped locally when the variables are unset).
- `image`: builds `linux/amd64` and `linux/arm64` with Buildx (GitHub Actions cache). Pull
  requests only build. Pushes to `main` publish `ghcr.io/<owner>/floorwars-api:<git sha>` and
  `:main` to GHCR using the workflow's `GITHUB_TOKEN`. Trivy scanning is added in Week 5.

`tests/test_migrations.py` is skipped unless `FLOORWARS_TEST_DATABASE_URL` points at a
PostgreSQL + PostGIS database. It migrates that database to head and back to base, so use a
throwaway one. `tests/auth` also needs `FLOORWARS_TEST_VALKEY_URL` (it truncates the auth tables
and flushes that Valkey database); the signature and token unit tests there run without either:

```sh
docker run -d --rm --name fw-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=floorwars \
  -p 55432:5432 postgis/postgis:18-3.6
docker run -d --rm --name fw-valkey -p 56379:6379 valkey/valkey:8
export FLOORWARS_TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/floorwars
export FLOORWARS_TEST_VALKEY_URL=redis://localhost:56379/0
python -m pytest -q tests/test_migrations.py tests/auth
docker stop fw-db fw-valkey
```

## Database and migrations

Schema: `app/db/models.py` (SQLAlchemy 2.0, GeoAlchemy2), migrations in `migrations/versions/`.
The baseline `0001_baseline` creates `user`, `device`, `team`, `season`, `team_membership`,
`building` and `refresh_token`, and enables the `postgis` and `citext` extensions. `0002_auth`
adds `otp_challenge` (hashed sign-in codes, `attempts` CHECK 0..5, a unique partial index
`ix_otp_challenge_email` for one active challenge per e-mail, and `ix_otp_challenge_email_created_at`
for cleanup), the nullable `user.terms_accepted_at`, `user.age_confirmed_at` and
`refresh_token.rotated_at`, and gives `device` the composite primary key `(user_id, id)` (it was
never deployed, so this reshaping was done in place).

Retention: `app.auth.repository.purge_expired(db, now)` deletes challenges older than one day and
refresh-token families whose every token has expired (revoked tokens of live families stay for
reuse detection). **TODO (Week 5):** schedule it daily with Celery beat; nothing runs it yet. Review notes and schema decisions:
[`docs/er_review.md`](docs/er_review.md).

From `server/`, with `FLOORWARS_DATABASE_URL` set:

```sh
python -m alembic upgrade head        # apply all migrations
python -m alembic check               # fail if models and migrations differ (drift)
python -m alembic downgrade -1        # undo the last migration (base = empty schema)
python -m alembic revision --autogenerate -m "short message"   # then review by hand
```

Notes:

- `user` is a reserved word in PostgreSQL; quote it (`"user"`) in hand-written SQL.
- The migration connection pins `search_path=public`, because the `postgis/postgis` image adds
  the `tiger` and `topology` schemas to it and Alembic would otherwise report their tables.
- Downgrading drops tables only; the `postgis` and `citext` extensions stay.
- `app/db/session.py` builds the sync engine `create_app` uses (decision 2026-10-31: handlers are
  plain `def`; an async engine would need `greenlet`). Pool 10 + 10 overflow, `pool_pre_ping`,
  `hide_parameters`.

## Endpoints

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness probe, returns `{"status": "ok"}`. No auth, no database access. |
| `GET /metrics` | Prometheus text format. **Stub** (`floorwars_up 1`) until Week 5 (plan 7.8). |
| `POST /v1/auth/otp` | Sends a 6-digit code to an allow-listed e-mail (no `+` sub-addresses: 422). 202, no body. 403 wrong domain, 429 rate limit (`Retry-After`; IP bucket first, then e-mail), 503 mail or Valkey down (fails closed). |
| `POST /v1/auth/verify` | Code, device and (new accounts) `accept_terms` + `confirm_adult` for a token pair. 401 wrong/expired, 403 confirmations missing (challenge stays usable), 429 after 5 attempts or per-IP limit, 503 Valkey down. |
| `POST /v1/auth/refresh` | Rotates the refresh token. 401 unknown, expired or reused; reuse revokes the whole family. 429 per-IP limit, 503 Valkey down. |

Auth details (plan 7.9): codes are `sha256(salt || code)` with a 16-byte salt, compared in
constant time, attempts counted under a row lock before comparing; a new request supersedes the
previous unused code only once the mail backend accepted the new one (if sending fails, 503, and
the previous code keeps working). New accounts get a neutral display name `Player-xxxx`, never
derived from the e-mail. Access tokens are EdDSA JWTs (`kid` = first 16 hex of SHA-256 of the public
key, `aud` checked, 15 minutes). Refresh tokens are 256-bit random values stored as SHA-256, each
rotation renews the 30-day lifetime; a rotated token presented again within
`FLOORWARS_REFRESH_REUSE_GRACE_S` is a retry (401, family kept), later it revokes the family. Devices are keyed by `(user_id, id)`: the same device id
signed in by two users gives two rows, and sign-in never moves a device between users. Codes and
tokens are never logged; database errors are logged as class, SQLSTATE and constraint only
(PostgreSQL error details repeat row values), and the engine hides bound parameters.

Per-IP limits run before any database work on all three routes. The bucket is the client address
for IPv4 and its /64 network for IPv6. Client IP: `request.client.host`. Behind Caddy, uvicorn only
trusts `X-Forwarded-For` from `--forwarded-allow-ips` (default `127.0.0.1`), so the deployment must
set `FORWARDED_ALLOW_IPS` to Caddy's address, or every request counts against Caddy's IP.

## Configuration

Settings are read from environment variables with the `FLOORWARS_` prefix (see `.env.example`).
When `/run/secrets` exists (deployed hosts, plan 7.5), a file named after the variable, lower-case
with the prefix, for example `/run/secrets/floorwars_database_url`, is read too (pydantic-settings
applies `env_prefix` to secret file names); secrets belong there, not in env files. Compose maps
the host files to these names, see `infra/secrets/README.md`.

| Variable | Default | Values / notes |
|---|---|---|
| `FLOORWARS_ENV` | `prod` | `dev`, `staging`, `prod`. Defaults to `prod` so a deployment that forgets it gets the strict startup checks; local runs and tests set `dev`. |
| `FLOORWARS_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `FLOORWARS_DATABASE_URL` | unset | PostgreSQL URL (`postgresql+psycopg://...`). Secret. Required by Alembic and the DB session. |
| `FLOORWARS_TEST_DATABASE_URL` | unset | Tests only: throwaway PostGIS database for the migration and auth tests. Not read by the app. |
| `FLOORWARS_VALKEY_URL` | unset | Valkey URL (`redis://[:password@]host:port/db`). Secret. Needed by `POST /v1/auth/otp` (rate limits). |
| `FLOORWARS_TEST_VALKEY_URL` | unset | Tests only: throwaway Valkey for `tests/auth` (flushed by the tests). Not read by the app. |
| `FLOORWARS_ALLOWED_EMAIL_DOMAINS` | `student.upt.ro` | Comma-separated e-mail domains that may sign in (case-insensitive, exact domain match). |
| `FLOORWARS_MAIL_BACKEND` | `log` | `acs` (Azure Communication Services, required in `prod`), `log` (dev: logs `otp mail sent to <address>`, never the code), `fake` (tests: in-memory outbox; refused in `staging`/`prod`). |
| `FLOORWARS_MAIL_FROM` | unset | Sender address of the ACS e-mail domain. Required with `acs`. |
| `FLOORWARS_ACS_ENDPOINT` | unset | `https://<resource>.communication.azure.com`. Required with `acs`. |
| `FLOORWARS_ACS_ACCESS_KEY` | unset | ACS access key (base64). Secret. Required with `acs`. |
| `FLOORWARS_JWT_SIGNING_KEY` | unset | Hex of a 32-byte Ed25519 seed (64 hex characters, one line, not a PEM). Secret. Required in `staging`/`prod`; in `dev` a random key per process is used. |
| `FLOORWARS_JWT_AUDIENCE` | `floorwars-api` | `aud` claim of access tokens; tokens with another audience are rejected. |
| `FLOORWARS_JWT_PREVIOUS_PUBLIC_KEYS` | empty | Key rotation: comma-separated raw Ed25519 public keys (64 hex each) of previous signing keys, still accepted for verification during the overlap. Not secret. Get one with `app.auth.tokens.public_key_hex(seed)`. |
| `FLOORWARS_ACCESS_TOKEN_TTL_S` | `900` | Access token lifetime (plan 7.9: 15 minutes). |
| `FLOORWARS_REFRESH_TOKEN_TTL_S` | `2592000` | Refresh token lifetime (30 days), renewed on every rotation. |
| `FLOORWARS_REFRESH_REUSE_GRACE_S` | `20` | A rotated refresh token presented again within this window is a retry: 401, family kept. Later it is reuse and revokes the family. |
| `FLOORWARS_OTP_TTL_S` | `600` | Sign-in code lifetime (plan 7.9: 10 minutes). |
| `FLOORWARS_OTP_MAX_ATTEMPTS` | `5` | Wrong codes allowed per challenge, 1 to 5 (the database CHECK caps it at 5). |
| `FLOORWARS_OTP_RATE_PER_EMAIL_PER_HOUR` | `5` | Token bucket size and hourly refill for code requests per e-mail. |
| `FLOORWARS_OTP_RATE_PER_IP_PER_HOUR` | `60` | Same, per client IP (IPv6 per /64). Students behind the campus NAT share one IP, so keep it generous. |
| `FLOORWARS_VERIFY_RATE_PER_IP_PER_HOUR` | `300` | Token bucket per client IP for `POST /v1/auth/verify`. |
| `FLOORWARS_REFRESH_RATE_PER_IP_PER_HOUR` | `1200` | Token bucket per client IP for `POST /v1/auth/refresh` (every signed-in phone refreshes about 4 times an hour). |
| `FLOORWARS_QR_HMAC_KEY` | unset | 32-byte HMAC key for entrance QR codes, hex. Secret. Checked by the check-in feature where it is used. |

All settings except `FLOORWARS_DATABASE_URL` are optional when `Settings` loads, because the
migration container receives only the database URL. Given values are format-checked (hex keys,
base64 ACS key, https endpoint). The API checks the rest at startup (`check_api_settings` in
`app/config.py`, called by `create_app`) and refuses to start when `FLOORWARS_ENV=prod` and the
mail backend is not `acs`, when `acs` lacks one of its three settings, when `staging`/`prod` lack
`FLOORWARS_JWT_SIGNING_KEY`, `FLOORWARS_DATABASE_URL` or `FLOORWARS_VALKEY_URL`, or when
`staging`/`prod` use the `fake` mail backend. Errors name the variable, never the value.
`app.main:app` is built lazily on first access, so importing `create_app` never runs the checks
against the process environment.

## Logging

Logs go to stdout as one JSON object per line (`timestamp`, `level`, `logger`, `message`, plus
any `extra` fields); uvicorn's access and error logs use the same format. Never log tokens,
passwords or connection strings.
