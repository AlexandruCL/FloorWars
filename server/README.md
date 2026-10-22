# FloorWars server

FastAPI backend (plan sections 4.1, 6 and 7). Current state: scaffold with `/healthz`,
a stub `/metrics`, settings and structured JSON logging. API routes will live under `/v1`.

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
| `FLOORWARS_DATABASE_URL` | unset | PostgreSQL URL (`postgresql+psycopg://...`). Secret. Optional for now. |
| `FLOORWARS_VALKEY_URL` | unset | Valkey URL (`redis://...`). Secret. Optional for now. |

## Logging

Logs go to stdout as one JSON object per line (`timestamp`, `level`, `logger`, `message`, plus
any `extra` fields); uvicorn's access and error logs use the same format. Never log tokens,
passwords or connection strings.
