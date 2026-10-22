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

Dependencies are declared in `pyproject.toml` (`dev` dependency group for test and lint tools).

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
