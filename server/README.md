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
When `/run/secrets` exists (deployed hosts, plan 7.5), a file named after the field, for example
`/run/secrets/database_url`, is read too; secrets belong there, not in env files.

| Variable | Default | Values / notes |
|---|---|---|
| `FLOORWARS_ENV` | `dev` | `dev`, `staging`, `prod` |
| `FLOORWARS_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `FLOORWARS_DATABASE_URL` | unset | PostgreSQL URL (`postgresql+psycopg://...`). Secret. Required by Alembic and the DB session. |
| `FLOORWARS_TEST_DATABASE_URL` | unset | Tests only: throwaway PostGIS database for `tests/test_migrations.py`. Not read by the app. |
| `FLOORWARS_VALKEY_URL` | unset | Valkey URL (`redis://...`). Secret. Optional for now. |

## Logging

Logs go to stdout as one JSON object per line (`timestamp`, `level`, `logger`, `message`, plus
any `extra` fields); uvicorn's access and error logs use the same format. Never log tokens,
passwords or connection strings.
