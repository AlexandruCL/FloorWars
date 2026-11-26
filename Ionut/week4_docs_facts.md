# W4 facts for w4-docs (lead notes, local; relay when resuming w4-docs)

## w4-read-api (W4-1, PR #83)
- GET /v1/seasons: JWT; array of Season, newest starts_at first (ties id desc); 401.
- GET /v1/me/segments?limit=1..100 (50)&cursor=: {items, next_cursor}; keyset (started_at, id) desc on (user_id, started_at DESC) index; cursor opaque base64url "started_at|id"; empty cursor = none; bad cursor/limit 422; next_cursor null on last page; reason = reject_reason or null.
- pending never returned; rejected past 200/h cap not stored (decisions 2026-11-20).
- GET /v1/me/season-stats?season_id=: default active; 404 no-active-season / season-not-found; 422 bad id; 401.
- Fields: team_id null w/o membership; steps_verified sum steps_scored verified; ascent_m sum verified ascent (2 dp); points incl. landing scans (after W4-4); rank competition rank (ties share), Valkey board with DB fallback, null without points; buildings_owned_by_team = building_claim rows of the team in the season; landmarks (server/app/me/landmarks.py): Statue of Liberty 93 m (NPS), Big Ben 96 m (UK Parliament), Eiffel 330 m (SETE), Empire State 381 m roof (ESRT), Burj Khalifa 828 m (Emaar/CTBUH); reached = ascent_m >= height_m. Scan points never in steps/ascent.

## w4-landing (W4-4)
- Sticker fwl1.<b64url(payload)>.<b64url(HMAC-SHA256)>; payload = entrance payload + "kind":"landing"; same key FLOORWARS_QR_HMAC_KEY; <=512 chars; nbf/exp <=31 days; entrance and landing never interchangeable.
- Tool: python tools/qr/make_entrance_qr.py --landing ... (same files <id>.svg, <id>.token.txt, --days cap 31).
- Rate limits: 6 attempts/user/hour (every attempt, bucket landing:user); 1 scored scan/user/building/10 min (bucket landing:building, only after token+check-in valid); 429 Retry-After; 503 when Valkey or QR key missing; no idempotency key.
- LANDING_SCAN_POINTS = 20; counted in team_building_score (steps 0), 7-day window (by scanned_at), Valkey boards, rebuild, DB fallback of GET /leaderboards.
- scanned_at replaced by server time when missing, >10 min old, >5 min ahead.
- 403 problem types: sticker-invalid, sticker-expired, sticker-wrong-building, no-checkin, season-inactive, no-team.
- Migration 0006_landing_scan (expand-only; downgrade drops all scans).

## w4-events (W4-2/3)
- server pings every 20 s (uvicorn default, Ionut 2026-11-20), answers client pings.
- GET /v1/me/events: every event of every season the user joined (team_membership for the event's season); event_id ascending, id > since; limit 1..100 (50); last_event_id = highest returned or since; has_more; 401; 422 for limit 0/101, negative since, since > 2^63-1. Items = WsEvent JSON; building_flipped equals the published event (team codes, `at` UTC ISO).
- Poll window (documented, Week 5 fix): ids assigned at insert, visible at commit; a poll with since >= 10 can miss #9 committed after #10 (ms window). Week 5: xid8 column + pg_snapshot_xmin filter in events_after.
- WS /v1/ws: Authorization: Bearer or access_token query, checked on the upgrade only; missing/invalid/expired token or deleted user -> HTTP 401 Problem on the upgrade (never 403, never close after accept); malformed since -> 422 on the upgrade; token expiring while open does not close it. Register with process hub, replay events_after(since) in pages of 100, then live; live events dedupe against the set of replayed ids (a lower id committed after the replay still arrives). At-least-once; client dedupes by event_id. Client messages ignored.
- Joined seasons read at connect; the app restarts the socket after a join (Cristea).
- Fan-out: one Valkey subscriber per process on fw:events; message = event + internal season_id, stripped before sending; same visibility rule as the feed.
- Limits: max 3 sockets per user per replica, a 4th closes the oldest with 1008; per-socket queue 256 events, full -> that socket closed 1008; send blocked > 10 s drops the socket; hub never waits on a socket.
- DB: only short thread-pool sessions (connect, one per replay page); none held while open.
- Failed publish after commit: live sockets miss that flip until reconnect; the 15-minute poll catches it; no retry queue.
- Logging: access_token value redacted to [redacted] in every log record (handler filter; uvicorn.error logs WS path+query, uvicorn.access HTTP queries). Caddy log deletes access_token query param; Authorization already REDACTED.
- Rolling deploy (runbook): deploy both replicas together (old replica publishes without season_id; new hub drops those; poll covers the gap).
- Week 5 season_state writer must store paused (bool) and ends_at (ISO) in game_event.payload, set season_id, and publish with season_id; otherwise event_json raises (500 on /me/events).
- WS route has name="openWebSocket" (websocket routes take no operation_id).

## w4-anticheat (W4-5, PR #86)
- Flag only: fraud_flag row with rule name; segment keeps verified + points; no new reason; no contract change; runs on newly verified segments under the user lock; at most one flag per segment and rule; constants in server/app/segments/rules.py; admin review Week 5.
- device_burst: > 60 batches per device_id per hour (token bucket seg:device, refilled hourly; skipped when Valkey is down; in practice only shared devices, per-user limit is also 60/h).
- device_shared: another user uploaded on the same device_id in the last 24 h (rolling).
- identical_segment: same user, verified, within 7 days either side, same steps, ascent_m within 0.01 m, duration_s within 0.1 s; the later one is flagged.
- impossible_sequence: nearest earlier or later verified segment in another building closer in time than footprint distance (ST_Distance geography) / MAX_WALK_SPEED_MPS (2.0).

## Other lead facts
- season-stats rank is competition rank (ties share); may differ from the leaderboard row number for tied players.
- Landing-scan points count in season-stats points and rank (Valkey and DB rank use leaderboards.POINTS_SOURCE) - branch feat/w4-stats-scan-points.
- Local stack fixed (PR #85): compose.local.yml dummy ACS endpoint, base64 placeholder; migrate: `docker compose -f docker-compose.yml -f compose.local.yml --profile tools run --rm --no-deps -T migrate alembic upgrade head`.
- Flaky test fixed (PR #87).
- Contract 0.9.0 final: season-stats 404 (no active / unknown season) + 422; /me/segments and /me/events 422; landing-scans 403 incl. no check-in, no running season, no team; 503; WS 422 for malformed since; events of every joined season.
