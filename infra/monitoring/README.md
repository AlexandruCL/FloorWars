# Monitoring (plan 7.8, W5-6)

Prometheus, Alertmanager, Grafana, Loki, Alloy, node_exporter, cAdvisor and postgres_exporter run
from `infra/docker-compose.yml` on the `monitoring` network. No port is published. Retention is
7 days for metrics and logs. Memory limits (sum about 1.6 GiB; measured use about 0.8 GiB on the local stack under light load: grafana 250 MiB, cadvisor 190, loki 160, prometheus 56, alloy 58): prometheus 384m, grafana 384m, loki
256m, alloy 192m, cadvisor 256m, postgres-exporter 64m, alertmanager 64m, node-exporter 48m.

| What | Where |
|---|---|
| App metrics | `GET /metrics` on each api replica (port 8000, internal network). Caddy answers 404 for `/metrics`. Prometheus finds both replicas by DNS (`api`) and scrapes them separately. |
| Dashboard | `grafana/dashboards/floorwars.json` (provisioned, "FloorWars"): traffic, errors, latency, the custom metrics, saturation, backups, certificate, logs. |
| Alerts | `alerts.yml` (rules) and `alertmanager.yml` (Discord, webhook from the secret file `discord_webhook_url`). |
| Logs | json-file container logs (tag = container name) read by Alloy, pushed to Loki. Query in Grafana: `{container=~".+"} \| json`. |
| Certificate and `/healthz` probe | Alloy's built-in blackbox exporter, probing `PROBE_URL` (default `https://$DOMAIN/healthz`), remote-written to Prometheus. It runs on the VM, so it cannot see a dead VM: the external monitor below does. |
| Backup age | metric `floorwars_backup_last_success_timestamp_seconds` in the node_exporter textfile volume `backup-textfile` (written by W5-7). The alert fires after 26 hours, and when the metric is missing. |

## Custom metrics (`server/app/metrics.py`)

`floorwars_http_requests_total{route,method,status}` and `floorwars_http_request_duration_seconds{route,method}` (route is the template, `unmatched` for unknown paths), `floorwars_segments_accepted_total`, `floorwars_segments_rejected_total{reason}`, `floorwars_detection_latency_seconds`, `floorwars_fraud_flags_total{rule}`, `floorwars_websocket_connections`, `floorwars_active_users` (distinct users with an upload receipt in the last 15 minutes, read from the database at scrape time, the same value on every replica: use `max`). No label holds a user, device, token or position. Queue depth is not exported yet (the Celery worker is W5-3).

Counters live in each API process and reset when a replica restarts: use `rate()`/`increase()`.

## Moving Grafana and Loki to another PC (decision Q5, if the VM has under 1.5 GiB free)

1. Move the `grafana` and `loki` service blocks and the `grafana-data`, `loki-data` volumes to a compose file on that PC. Remove the `GRAFANA_DOMAIN` site from the Caddyfile or leave it unused.
2. On the PC, Grafana's Prometheus datasource must reach the VM's Prometheus: publish Prometheus on the VM bound to a WireGuard or SSH-tunnel address only, never on the public interface (not set up here).
3. Set `LOKI_URL` in the VM's `infra/.env` to the PC's Loki push address; the log push needs a reachable address too (same tunnel).
4. Alerts stay on the VM (Prometheus and Alertmanager), so they work with the PC off.

## Images (decision Q12b: newest tag at least 14 days old on the install day)

Looked up on 2026-11-28 (a tag must have been pushed on or before 2026-11-14 to qualify):

| Image | Pinned | Pushed | Note |
|---|---|---|---|
| prom/prometheus | v3.16.0 | 2026-11-05 | ok |
| prom/alertmanager | v0.35.0 | 2026-11-09 | v0.35.1 (11-24) too new |
| grafana/grafana | 13.3.1 | 2026-11-10 | 13.3.2 (11-24) too new |
| grafana/loki | 3.7.10 | 2026-11-13 | 3.7.11 (11-27) too new |
| grafana/alloy | v1.22.0 | 2026-11-13 | ok |
| prom/node-exporter | v1.13.1 | 2026-11-19 | only 1.13.x tag; old enough from 2026-12-03 |
| ghcr.io/google/cadvisor | v0.61.1 | 2026-11-18 | 0.61.0 is 11-16; old enough from 2026-12-02 |
| prometheuscommunity/postgres-exporter | v0.21.1 | 2026-11-18 | only 0.21.x with 0.21.0 absent on Docker Hub; old enough from 2026-12-02 |

Re-check the three "too new" rows on the install day. If the install is earlier, the approved minors have no old-enough tag: ask Ionut before falling back to node-exporter v1.12.1, postgres-exporter v0.20.1 or cAdvisor v0.60.6.

## Steps for Ionut (secrets and accounts: yours only)

1. **Discord webhook.** Discord: Server Settings > Integrations > Webhooks > New Webhook, pick the alert channel, copy the URL. Add it as `discord_webhook_url=<URL>` to a new `infra/secrets/monitoring.enc.env` (SOPS, same flow as the other secrets), together with `grafana_admin_password=<random>`, `exporter_db_password=<random>` and `grafana_basic_hash=<output of docker run --rm caddy:2 caddy hash-password>` (choose a basic-auth password; user name is `team`). `deploy.sh` writes each as a file; the containers run as non-root users, so the files must be readable by uid 65534 (alertmanager, postgres-exporter) and 472 (grafana); Caddy reads `grafana_basic_hash` as root. Tell w5-ops-sec if deploy.sh needs a per-file owner.
2. **Postgres monitor role** (once, as `postgres` on the VM): `CREATE ROLE floorwars_monitor LOGIN PASSWORD '<exporter_db_password>' ; GRANT pg_monitor TO floorwars_monitor;` (pass the password through `\set` as `roles.sql` does, not on a command line).
3. **DNS and `.env`:** an A record `grafana.<domain>` to the VM; in `infra/.env`: `GRAFANA_DOMAIN`, `TEAM_IPS` (the two team addresses; the faculty NAT address is one client).
4. **Test alert:** after deploy, `docker compose exec alertmanager amtool alert add test severity=page --annotation=summary="test alert" --alertmanager.url=http://localhost:9093` and check the Discord channel (resolve or wait for it to expire).
5. **External uptime monitor (Q17):** sign up for a free HTTP monitor (for example UptimeRobot or Better Stack, free tier, no card), add an HTTPS monitor on `https://api.<domain>/healthz` every 5 minutes expecting 200, and its Discord integration pointing at the same channel (or the same webhook URL). Do not give it any credentials.
