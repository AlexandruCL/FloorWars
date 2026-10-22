# infra

Deployment and operations for the FloorWars backend (owner: Ionut; plan sections 7 and 9.1).
This directory is a placeholder; its contents arrive in later branches.

What will live here:

- **Docker Compose** files for the single Azure VM: two API replicas, Celery worker,
  PostgreSQL 18 + PostGIS, Valkey (plan 7.1 to 7.3). Images are multi-stage, non-root,
  multi-arch, pushed to GHCR.
- **Caddy 2** config: TLS via Let's Encrypt, HSTS and security headers, per-IP limits,
  load balancing with active health checks on `/healthz` (plan 7.4).
- **`deploy.sh`**: deploy a git SHA, run expand-only migrations, `docker compose up -d --wait`,
  automatic rollback to `/srv/floorwars/last_good` on failed health checks (plan 7.6).
- **Secrets**: SOPS + age encrypted files, decrypted by `deploy.sh` to `/run/secrets` and
  mounted through Compose `secrets:`; never in env files, images or CI logs (plan 7.5).
- **Monitoring**: Prometheus, Grafana dashboards, Loki + Alloy, Alertmanager rules,
  and the backup (pgBackRest) configuration (plan 7.7 and 7.8).
