# FloorWars server

FastAPI backend (plan sections 4.1, 6 and 7). Current state: scaffold with `/healthz`,
a stub `/metrics`, settings, structured JSON logging and the baseline database schema
(Alembic). API routes will live under `/v1`.

## Run

From `server/`, with the project venv active (Python 3.13):

```sh
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
  `ruff check`, `ruff format --check`, `mypy app` and `pytest -q`. A `postgis/postgis:18-3.6`
  service container is started and `FLOORWARS_TEST_DATABASE_URL` is set, so database and
  migration tests run in CI (they are skipped locally when the variable is unset).
- `image`: builds `linux/amd64` and `linux/arm64` with Buildx (GitHub Actions cache). Pull
  requests only build. Pushes to `main` publish `ghcr.io/<owner>/floorwars-api:<git sha>` and
  `:main` to GHCR using the workflow's `GITHUB_TOKEN`. Trivy scanning is added in Week 5.

`tests/test_migrations.py` is skipped unless `FLOORWARS_TEST_DATABASE_URL` points at a
PostgreSQL + PostGIS database. It migrates that database to head and back to base, so use a
throwaway one:

```sh
docker run -d --rm --name fw-db -e POSTGRES_PASSWORD=test -e POSTGRES_DB=floorwars \
  -p 55432:5432 postgis/postgis:18-3.6
export FLOORWARS_TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/floorwars
python -m pytest -q tests/test_migrations.py
docker stop fw-db
```

## Database and migrations

Schema: `app/db/models.py` (SQLAlchemy 2.0, GeoAlchemy2), migrations in `migrations/versions/`.
The baseline `0001_baseline` creates `user`, `device`, `team`, `season`, `team_membership`,
`building` and `refresh_token`, and enables the `postgis` and `citext` extensions. Review notes
and schema decisions: [`docs/er_review.md`](docs/er_review.md).

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
- `app/db/session.py` has a sync engine for now: the async engine needs `greenlet`
  (`sqlalchemy[asyncio]`), which is not a declared dependency yet.

## Endpoints

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness probe, returns `{"status": "ok"}`. No auth, no database access. |
| `GET /metrics` | Prometheus text format. **Stub** (`floorwars_up 1`) until Week 5 (plan 7.8). |

## Configuration

Settings are read from environment variables with the `FLOORWARS_` prefix (see `.env.example`).
When `/run/secrets` exists (deployed hosts, plan 7.5), a file named after the variable, lower-case
with the prefix, for example `/run/secrets/floorwars_database_url`, is read too (pydantic-settings
applies `env_prefix` to secret file names); secrets belong there, not in env files. Compose maps
the host files to these names, see `infra/secrets/README.md`.

| Variable | Default | Values / notes |
|---|---|---|
| `FLOORWARS_ENV` | `dev` | `dev`, `staging`, `prod` |
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
| `FLOORWARS_ACCESS_TOKEN_TTL_S` | `900` | Access token lifetime (plan 7.9: 15 minutes). |
| `FLOORWARS_REFRESH_TOKEN_TTL_S` | `2592000` | Refresh token lifetime (30 days), renewed on every rotation. |
| `FLOORWARS_OTP_TTL_S` | `600` | Sign-in code lifetime (plan 7.9: 10 minutes). |
| `FLOORWARS_OTP_MAX_ATTEMPTS` | `5` | Wrong codes allowed per challenge, 1 to 5 (the database CHECK caps it at 5). |
| `FLOORWARS_OTP_RATE_PER_EMAIL_PER_HOUR` | `5` | Token bucket size and hourly refill for code requests per e-mail. |
| `FLOORWARS_OTP_RATE_PER_IP_PER_HOUR` | `60` | Same, per client IP. Students behind the campus NAT share one IP, so keep it generous. |
| `FLOORWARS_QR_HMAC_KEY` | unset | 32-byte HMAC key for entrance QR codes, hex. Secret. Checked by the check-in feature where it is used. |

All settings except `FLOORWARS_DATABASE_URL` are optional when `Settings` loads, because the
migration container receives only the database URL. Given values are format-checked (hex keys,
base64 ACS key, https endpoint). The API checks the rest at startup (`check_api_settings` in
`app/config.py`, called by `create_app`) and refuses to start when `FLOORWARS_ENV=prod` and the
mail backend is not `acs`, when `acs` lacks one of its three settings, when `staging`/`prod` lack
`FLOORWARS_JWT_SIGNING_KEY`, or when `staging`/`prod` use the `fake` mail backend. Errors name the
variable, never the value.

## Logging

Logs go to stdout as one JSON object per line (`timestamp`, `level`, `logger`, `message`, plus
any `extra` fields); uvicorn's access and error logs use the same format. Never log tokens,
passwords or connection strings.
