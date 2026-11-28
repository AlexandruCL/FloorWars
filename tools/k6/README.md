# k6 load test (W5-8)

`load.js` runs two scenarios against the **local** compose stack: batched `POST /v1/segments`
(3 segments per request, a fresh `Idempotency-Key` each, many users) and N WebSockets on `/v1/ws`
counting the flip frames they receive. **Never run it against the VM** (testers use it). One short
low-rate smoke against the VM only with Ionut's go (`-e SCENARIO=smoke`, 3 requests, one user that
Ionut creates himself; `seed_users.py` refuses `FLOORWARS_ENV=prod`).

k6 1.8.3 is a local tool: install it on the PC (`winget install k6`, then `k6 version`).

## Run (one local stack at a time on this PC)

```sh
cd infra
docker compose -f docker-compose.yml -f compose.local.yml up -d --build --wait
docker compose -f docker-compose.yml -f compose.local.yml --profile tools run --rm --no-deps -T migrate alembic upgrade head
# 200 users with tokens (they last 15 minutes: seed right before the run)
docker compose -f docker-compose.yml -f compose.local.yml exec -T api python - 200 < ../tools/k6/seed_users.py > ../tools/k6/users.json
cd ../tools/k6
k6 run -e SCENARIO=smoke -e BASE_URL=http://localhost:8080 load.js     # check the script first
k6 run -e BASE_URL=http://localhost:8080 -e PEAK_RPS=60 -e SOCKETS=100 load.js
```

The run is 4.5 minutes. Each seeded user has a full upload bucket of 60 requests, so a user sends
at most 50. Watch Grafana (`http://localhost:3001`, user `team`, password `local`) during the run.
Record into `docs/evaluation.md`: requests per second, p50/p95/p99 (`http_req_duration` for the
`POST /v1/segments` name), error rate, sockets held (`fw_sockets_opened`, the dashboard's
WebSocket panel), the first resource to saturate (container CPU and memory panels), the date, the
machine (CPU, RAM, Docker Desktop memory limit) and the commit. `users.json` holds tokens and is git-ignored.
