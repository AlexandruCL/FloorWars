# infra

Deployment and operations for the FloorWars backend (owner: Ionut; plan sections 7 and 9.1).
Week 1 scope: Caddy, two API replicas, PostgreSQL 18 + PostGIS, Valkey on one Azure VM.
VM setup, first deploy and rollback: `docs/runbook.md`. Costs: `docs/cost.md`.

## Layout

| Path | What |
|---|---|
| `docker-compose.yml` | Production stack. Networks `edge` (Caddy), `app` (api), `data` (postgres, valkey; `internal: true`), `monitoring` (Week 5). Only Caddy publishes ports (80, 443, 443/udp). Needs `API_TAG`. |
| `compose.local.yml` | Override for a dev PC: builds `api` from `../server`, Caddy on `127.0.0.1:8080` (plain HTTP), dummy secrets, named volume for Postgres. |
| `caddy/Caddyfile` | TLS (Let's Encrypt), HSTS and security headers, round robin over every api replica with active `/healthz` checks, `/metrics` not public. Per-IP rate limiting: TODO Week 5 (needs a plugin build). |
| `deploy.sh` | `deploy.sh <sha>` / `deploy.sh rollback` (plan 7.6). Forced SSH command of the `deploy` user. |
| `secrets/` | SOPS + age encrypted `*.enc.{env,json,yaml}`; see `secrets/README.md`. `.sops.yaml` is at the repo root. |
| `scripts/make-local-secrets.sh` | Writes dummy `local-secrets/*` and a local `.env` (`API_TAG=local`) for the local stack. |
| `.env.example` | Non-secret per-host values (`DOMAIN`, `ACME_EMAIL`, `FLOORWARS_ENV`, ...). Copy to `.env` (git-ignored). |

Hardening in compose: api and valkey run non-root with `read_only: true`, `tmpfs: /tmp`,
`cap_drop: [ALL]`, `no-new-privileges`; Caddy keeps only `NET_BIND_SERVICE`. Secrets are Compose
file secrets mounted under `/run/secrets`, never environment variables, so `docker inspect`
does not show them. The api reads them as `/run/secrets/floorwars_<field>` (pydantic-settings
applies the `FLOORWARS_` prefix to secret file names). Logs are rotated (json-file, 5 x 10 MB).

## Run locally

Requires Docker Desktop (or Engine) with Compose v2.24+. Uses only `postgis/postgis:18-3.6`,
`valkey/valkey:8`, `caddy:2` and the images the server `Dockerfile` builds from. From the repo
root, in Git Bash or any POSIX shell:

```sh
bash infra/scripts/make-local-secrets.sh
cd infra
docker compose -f docker-compose.yml -f compose.local.yml up -d --build --wait
curl -s http://localhost:8080/healthz                # {"status":"ok"} through Caddy
docker compose -f docker-compose.yml -f compose.local.yml ps
docker compose -f docker-compose.yml -f compose.local.yml exec postgres \
  psql -U postgres -d floorwars -c "select postgis_version()"
docker compose -f docker-compose.yml -f compose.local.yml down -v   # also drops the local DB
```

The PostGIS extension is created in the `floorwars` database (the image's init script), so use
`-d floorwars`. Check the production file renders: `API_TAG=test docker compose -f
docker-compose.yml config -q` (needs the secret files under `SECRETS_DIR` to exist).

## Deploy (VM)

`deploy.sh <sha>`: lock; check out `<sha>` (must be on `origin/main`); decrypt
`secrets/*.enc.*` into `/run/secrets/floorwars` (tmpfs, mode 0400, owned by the reading
container's uid); pull; start postgres and valkey; `alembic upgrade head` (expand-only, skipped
while the image has no `alembic.ini`); `docker compose up -d --wait` within 90 s; record the
tag in `/srv/floorwars/current` and the previous one in `/srv/floorwars/last_good`. On failure it
re-pins `last_good` without migrations. `deploy.sh rollback` re-pins `last_good` on demand.

## Later

- Week 2: Celery `worker` (same image, networks app + data), separate migration and app DB
  roles, JWT/QR/e-mail secrets.
- Week 4: `scheduler` (Celery beat), FCM service account secret on the worker.
- Week 5: monitoring stack (Prometheus, Grafana, Loki, Alloy, Alertmanager, node_exporter,
  cAdvisor, postgres_exporter) on the `monitoring` network, `admin` (SQLAdmin) and Grafana
  behind Caddy IP allowlists, pgBackRest to Azure Blob, Caddy per-IP rate limits, Trivy in CI.
