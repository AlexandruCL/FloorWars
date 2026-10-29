# FloorWars: Project Reference and 6-Week Implementation Plan

This file is the single source of truth for the project. It replaces `Mobile_Project_Pitch_Ideas.pdf` (53 pages, deleted from the repo). Everything the PDF said about FloorWars, plus the shared engineering baseline it relied on, is here. When this file and the code disagree, fix one of them in the same PR.

Team: **Cristea** (Member A) and **Ionut** (Member B).
Client: **React Native**, Android first. The PDF assumed Kotlin and a team of 3 to 4. We changed the client technology and the team size, so the plan and the scope are ours; everything else comes from the PDF.
Plan length: 6 weeks. Week 1 starts the week of 19 October 2026.

Conventions used below:

- "PDF" marks a decision or number taken from the original pitch.
- "Ours" marks a decision we added or changed (React Native, 2-person split, proposed endpoints, thresholds to tune).
- Numbers marked "tune" are starting guesses. We fix them from labelled traces.

## Contents

1. Product
2. Game rules
3. Architecture
4. Tech stack and React Native decisions
5. Data model
6. API contract
7. Infrastructure and operations
8. Security and privacy
9. Team split and working rules
10. Six-week plan
11. Evaluation plan
12. Risks and mitigations
13. Launch, marketing, monetization
14. Presentation outline and academic angle
15. Appendix: original milestones, scope cuts, open decisions, glossary, sources

---

## 1. Product

### 1.1 Pitch

FloorWars: **Take the stairs, take the building.** A campus territory game in which every sensor-verified stair climb adds points to your faculty's claim on a real building.

### 1.2 Problem and niche

Students and office workers sit most of the day. In multi-storey faculty buildings the default is the elevator. Stair climbing is one of the cheapest health interventions, and organisations already run stair challenges (UBC "Pick Your Peak", UCL "Bentham Conquers Ben Nevis"). Those run on spreadsheets, honour-system logs, or posters. The best-known product, StepJockey, needed NFC smart signs installed on every staircase. Phones already hold a barometer that resolves a single floor, but no consumer product turns that signal into a social, place-based reason to take the stairs.

Niche: university students in multi-storey campuses. UPT (Politehnica University of Timisoara) has many faculty buildings, and each faculty has a strong identity. A later B2B extension targets office towers.

Why it is interesting technically: fusing a noisy pressure sensor with step detection, running reliably in the background under Android battery restrictions, and resisting cheating, all wrapped in a game loop students already understand (faculty rivalry).

### 1.3 Competitors and the gap

| Existing product | What it does | Gap FloorWars fills |
|---|---|---|
| StepJockey (UK, 2013) | NFC smart signs on office staircases show calories burned; the app records stair use for employer challenges. | Needs hardware on every staircase; no territory mechanic; aimed at HR departments, not students. |
| "Floors climbed" in Apple Health, Google Fit, Fitbit | Personal floor count from barometer plus motion. | Personal metric only; no building context, no teams, no verification against elevators or cheating. |
| Manual workplace and campus challenges (UBC, UCL, Vantage Fit guide) | Logs or trackers for climbing a "virtual mountain" over weeks. | Honour system, high organiser effort, no live competition. |
| Stair-themed mobile games (To The Highest Floor, Endless Climb) | Virtual stair-running arcade games. | No real-world movement at all. |

The gap: no product combines hardware-free, sensor-verified stair detection with a building-aware territory game and team rivalry.

### 1.4 Audience

Primary: undergraduates aged 19 to 24 at a multi-faculty technical university.

Persona: Ioana, 20, second-year student. Her classes are on the upper floors of her faculty building and she waits for the elevator between back-to-back lectures. She does not go to the gym regularly but feels she should move more. She spends her online time on Instagram and TikTok (faculty memes, "day in my life" student content), in her year group's Discord or WhatsApp, and follows the student organisation's page. She is competitive about her faculty in a light-hearted way. Her pain point: "taking the stairs" is good advice with no reward, no social proof, and no fun. FloorWars gives each climb a visible effect (her faculty's colour spreading across a building) and a reason to bring friends.

Behaviours the design relies on: short sessions between classes; strong group identity by faculty and year; content creation around campus life; response to weekly events and leaderboards.

### 1.5 Features

MVP (PDF, one semester; we deliver the subset marked in section 10):

- Sign-up with a one-time code sent to the university student e-mail domain. The domain check blocks outsiders and duplicate accounts. Then a choice of faculty team for the season.
- Building check-in by scanning a printed QR code at the building entrance (signed, rotating token), or by geofence when GPS accuracy allows. This sets the "current building" for 90 minutes.
- Background climb detection in an Android foreground service: barometer at 10 to 25 Hz plus the hardware step detector; on-device segmentation into ascent windows; classification as stairs, elevator, or other.
- Building claims: each verified stair step adds points for your team in that building. The team with the most points in the rolling 7-day window owns the building. A building standings view shows each team's share in team colours, updated live over WebSocket. No floor numbers are shown or stored; the app does not need building floor data.
- Leaderboards for individuals, teams and buildings, plus season-long progress converted into landmarks ("your faculty climbed the Eiffel Tower 3.2 times").
- Shareable 9:16 cards generated on the device: building standings, personal stats, "building flipped" moments.
- Fallback for phones without a barometer: small QR stickers on stair landings ("scan at the stairs of building X") with rate limits.
- Admin panel (web, team-only) to draw building footprints, manage seasons, and review fraud flags. No floor counts or heights.
- Notification to a team that lost a building, delivered by our own channel (WebSocket from the sensing service, plus a polling fallback; no Firebase, see 7.2.1).

Stretch (PDF): iOS client (Core Motion altimeter and pedometer), "raids" (one-hour team events with double points), achievements, Play Integrity attestation, on-device ML classifier v2 trained on pilot data, office-tower "corporate mode" with private leagues.

Out of scope (PDF): indoor positioning of individual staircases, payments, chat, iOS in the MVP, wearables.

---

## 2. Game rules

| Rule | Value | Source |
|---|---|---|
| Season length | Two-week rounds. A one-week "Faculty Wars Week" season is used for the launch. | PDF |
| Teams | One team per user per season. Teams are faculties (codes such as AC, ETC, MEC) with a colour. | PDF |
| Building ownership | The team with the most points in that building over the rolling 7 days owns it. | PDF, adapted (ours) |
| Points | Per verified stair step. No reward for speed. Diminishing returns per hour. Elevator rides and flat walking score nothing. | PDF, adapted (ours) |
| Point values and the diminishing curve | Start at 1 point per verified step, halving after 300 steps in an hour, tune. | Ours |
| Floor-equivalent (display only) | 20 verified steps = 1 floor-equivalent, so a team with 200 steps in a building shows "10 floors". An estimate, about 6 steps per metre times a 3.3 m storey, tuned from real data. Never a real storey number, and no building floor data is used. Every screen that shows it says "floors (estimate)". | Ours |
| Check-in validity | 90 minutes from check-in. Segments are attributed to the building of the active check-in. | PDF |
| Segment attribution | A segment needs an active check-in to count. | PDF |
| Per-user limits | At most 60 segment uploads per hour and at most 600 verified steps per 10 minutes. These double as anti-cheat signals. | PDF, adapted (ours) |
| Segment bounds | `steps` between 1 and 2000; `ascent_m` between 2.0 and 120.0; a segment counts only if its pressure change matches its steps (section 3.2). | PDF, adapted (ours) |
| Age | Users under 18 are not accepted. | PDF |
| Accessibility | An accessible contribution mode (points for walking steps or for supporting actions). Copy never shames elevator use. | PDF mitigation, rules ours |
| Safety | Safety copy in onboarding. No speed rewards. Hourly caps. | PDF |
| Season close | One transaction snapshots final claims into a results table. | PDF |

---

## 3. Architecture

```
Android app (React Native + Kotlin native module)
  Sensor service (foreground, type health)
    barometer 10-25 Hz + step detector
    Segmenter: pressure smoothing, ascent windows
    Classifier: rules v1 (LiteRT model v2 is a stretch)
    Room/SQLite outbox
  JS layer: sync worker (backoff + idempotency), UI, WebSocket client
        |  POST /v1/segments (batch, Idempotency-Key)
        |  GET  /v1/buildings/{id}/standings
        v
FastAPI (2 replicas behind Caddy)
  plausibility checks: speed, cadence, steps/m, rate, pressure-steps match
  DB transaction: insert segment, add points, lock + update building_claim
        |                         |
        v                         v
PostgreSQL 18 + PostGIS       Valkey: ZINCRBY leaderboards, PUBLISH building_flipped
                                  |
                                  v
                          WS hub (inside api) -> phones
                          game_event table -> WS replay / GET /v1/me/events -> local notification
```

### 3.1 Climb-to-claim sequence

1. Building context is set by QR or geofence check-in (valid 90 minutes).
2. Phone sensors emit pressure and step events.
3. The segmenter detects an ascent window, computes features and `stair_prob`.
4. The segment is stored in the Room outbox with a client UUID.
5. The sync worker sends `POST /v1/segments` as a batch with an `Idempotency-Key`.
6. The API validates schema and plausibility rules.
7. Transaction begins. Insert the segment `ON CONFLICT DO NOTHING`.
8. Upsert `team_building_score` (+points for the verified steps).
9. `SELECT ... FROM building_claim WHERE season_id = $1 AND building_id = $2 FOR UPDATE`, then set the owner to the team with the highest score. Commit.
10. `ZINCRBY` season leaderboards, `PUBLISH building_flipped`.
11. Response `200 {accepted, rejected, flips}`.
12. The WebSocket hub pushes `"AC took the Politehnica building"` to connected phones; the event is stored in `game_event`, so phones that were offline get it on reconnect or at their next poll and show a local notification (7.2.1).

### 3.2 Other data flows

- Check-in: QR scan, `POST /v1/checkins` with the signed token. The server verifies the HMAC and its time window, then creates a check-in row with a 90-minute validity range.
- Share card: `GET /v1/me/season-stats`, the app renders the card locally (no image server), then the Android share sheet.

### 3.3 Sensor fusion

- Near sea level, pressure falls about 0.12 hPa per metre. A 3.2 m storey is about 0.38 hPa, well above the noise of a smoothed phone barometer. The app works in metres of ascent, not building floors, so no storey height is needed.
- Weather moves pressure slowly, so ascent is measured only over short windows (seconds to a few minutes). Weather drift becomes negligible.
- Stairs and elevators separate on two features:
  - Vertical speed: stairs are typically well under 1 m/s, elevators faster.
  - Steps per metre of ascent: stair steps are 15 to 18 cm, so stairs give roughly 6 steps per metre. An elevator gives almost none.
- Car rides on hills are excluded by GPS speed and the absence of steps.
- Shaking the phone produces steps without ascent. Blowing on the sensor produces pressure spikes without steps.
- **Points need a matching pressure change.** A segment scores only if its steps and its pressure change agree: stairs need both a rise in metres and steps at about 6 per metre. Steps with no ascent (shaking, flat walking) score nothing. Ascent with no steps (elevator, or a lift-like rise) scores nothing.
- Exact thresholds are tuned on labelled pilot data and on the synthetic and real traces (`docs/trace_format.md`). Precision and recall against hand-labelled climbs go into the final report.
- Server-side checks repeat the plausibility rules, because a modified client cannot be trusted.

Starting thresholds for the rules classifier (ours, all tune):

| Feature | Stairs | Elevator | Other |
|---|---|---|---|
| Vertical speed | 0.1 to 0.9 m/s | above 1.0 m/s | outside both |
| Steps per metre of ascent | 4 to 8 | below 1 | steps without ascent, or ascent without steps |
| Window length | 5 s to 3 min | any | any |
| Points awarded | steps in the window, if both features match | none | none |

### 3.4 Anti-cheat layers

1. On-device: classifier rejects non-stair patterns before upload.
2. Server plausibility: speed, cadence, steps per metre, pressure-steps match, rate limits.
3. Valkey token bucket per user (60 uploads/hour, 600 verified steps/10 minutes).
4. Per-device limits and `fraud_flag` rows reviewed in the admin panel.
5. Signed expiring QR tokens so photographed codes cannot be reused remotely.
6. Stretch: Play Integrity attestation against emulators and modified clients.

---

## 4. Tech stack and React Native decisions

### 4.1 Stack

| Layer | Choice | Reason |
|---|---|---|
| Mobile client | React Native (bare, TypeScript), Android first | Team choice (ours). |
| Native sensing | Kotlin native module plus foreground service of type `health`: `SensorManager` `TYPE_PRESSURE` and `TYPE_STEP_DETECTOR`, Room outbox, WorkManager sync | PDF reasoning: background sensing needs native control over services, wake-ups and battery. Ours: we keep that part in Kotlin and wrap it for RN. |
| On-device classifier | Rule-based v1; LiteRT (TensorFlow Lite) model v2 trained on labelled pilot climbs (stretch) | Rules are explainable for the first demo; a model improves recall later without a server round-trip. Raw sensor streams are never sent to a server. |
| Backend API | FastAPI (Python 3.13), Pydantic v2 strict, SQLAlchemy 2.0, team-written JWT/refresh service | Async I/O for batched uploads plus WebSockets; precise validation errors. |
| Database | PostgreSQL 18 + PostGIS 3.6 | Relational integrity for teams, seasons, claims; PostGIS for footprints and geofence; declarative partitioning for climb data. |
| Cache / broker | Valkey (sorted sets for leaderboards, token buckets for rate limits, pub/sub for WebSocket fan-out) + Celery workers | Leaderboards are a sorted-set problem; pub/sub lets two API replicas share live events. |
| Hosting | One Azure VM, Docker Compose, Caddy 2 | Ours. PDF used an Oracle free VM. We keep the same self-managed model; the cloud only supplies infrastructure primitives. |
| CI/CD | GitHub Actions, GHCR, SSH deploy script | See section 7. |
| Monitoring | Prometheus, Grafana, Loki + Alloy, Alertmanager; custom metrics for segments accepted vs rejected and detection latency | Lets us show detection quality and fraud rates as live dashboards in the demo. |
| Notifications | Own channel: `game_event` table, WebSocket from the Kotlin sensing service with replay, WorkManager polling fallback, local Android notifications | Needed to tell a team it lost a building. No Firebase or managed push service (course rule, section 7.2.1). |
| Cloud provider | Azure, infrastructure primitives only (section 7.2) | Ours. Replaces the PDF's Oracle VM. |

Deliberately not used: Firebase as a platform (database, auth, analytics, crashlytics, hosting), Supabase, Appwrite, Back4App, Vercel, Netlify, Heroku, Render, Railway, and managed backend, auth or database services from Azure. No Firebase in any form, including FCM (course rule, 2026-10-29). Narrow external services that remain: an outbound e-mail service for one-time codes (Azure Communication Services or an SMTP relay; self-hosted mail has no sending reputation), and Blob Storage for backups.

### 4.2 React Native libraries (ours)

| Concern | Library or approach |
|---|---|
| Navigation | React Navigation |
| Server state | TanStack Query |
| Local UI state | Zustand |
| Generated API client | `openapi-typescript` from `/contracts/openapi.yaml` |
| Token storage | `react-native-keychain` (Android Keystore) |
| QR scanning | `react-native-vision-camera` with the code scanner |
| Check-in location | `react-native-geolocation-service`, one-shot fix, never continuous |
| Standings drawing and animation | `react-native-svg` + Reanimated |
| Share cards | `react-native-view-shot` + `react-native-share` |
| Notifications | No library: the Kotlin service posts Android notifications with `NotificationManager`; WorkManager for the polling fallback. No Firebase. See 7.2.1. |
| Tests | Jest + React Native Testing Library; JUnit for Kotlin; pytest for the backend |

### 4.3 Why part of the client is Kotlin

The PDF rejected cross-platform frameworks because their sensor plugins rarely sample reliably in the background. We keep React Native and remove that risk this way:

- The Kotlin service owns sensor registration, the segmenter, the classifier and persistence. The JS runtime may be killed at any moment, and nothing about detection depends on it.
- The native module exposes a small API to JS: `start()`, `stop()`, `getStatus()`, `getPending(limit)`, `markSynced(ids)`, `setConfig(json)`, `startLogging(label)`, `stopLogging()`, plus events for status changes.
- The segmenter is a pure Kotlin class with no Android imports, so JUnit can replay recorded traces in CI.
- Pin the React Native version in Week 1 and do not upgrade during the project.
- Use no Expo Go. A development build is required either way.

---

## 5. Data model

Third normal form. The only derived data are `team_building_score` and `building_claim`, maintained transactionally and rebuildable from `climb_segment` at any time.

### 5.1 Entities

| Table | Columns (key ones) | Notes |
|---|---|---|
| `user` | `id uuid PK`, `email citext UNIQUE`, `display_name text`, `created_at timestamptz` | |
| `device` | `id uuid PK`, `user_id FK`, `model text`, `has_barometer bool`, `last_seen_at` | One user, several devices. |
| `team` | `id int PK`, `code text UNIQUE` (e.g. AC, ETC, MEC), `color_hex text` | A faculty. |
| `season` | `id int PK`, `active_during tstzrange` with EXCLUDE (no overlap) | Seasons never overlap. |
| `team_membership` | `user_id PK/FK`, `season_id PK/FK`, `team_id FK` | Composite PK gives exactly one team per user per season. |
| `building` | `id int PK`, `name text`, `footprint geometry(Polygon, 4326)` with GiST | No floor count or heights: the app does not need building floor data. |
| `checkin` | `id uuid PK`, `user_id FK`, `building_id FK`, `method text` (`qr` or `geofence`), `valid_during tstzrange` | |
| `climb_segment` | `id uuid` (client-generated), `device_id FK`, `user_id FK`, `checkin_id FK`, `building_id FK`, `steps_scored smallint`, `ascent_m real`, `vert_speed_mps real`, `steps smallint`, `stair_prob real`, `status text` (`pending`, `verified`, `rejected`), `started_at timestamptz` (partition key, monthly), `UNIQUE(device_id, id)` | Core fact table. |
| `fraud_flag` | `id bigint PK`, `segment_id FK`, `rule text`, `created_at`, `resolved_at` | |
| `team_building_score` | `season_id`, `building_id`, `team_id` (composite PK), `points int` | Derived. |
| `building_claim` | `season_id`, `building_id` (composite PK), `team_id FK`, `claimed_at` | Derived. Current owner per season and building. |
| `refresh_token` | `id uuid PK`, `user_id FK`, `token_hash bytea UNIQUE`, `family_id uuid`, `revoked_at` | |

Our additions (not in the PDF ER diagram): a `config` table of versioned classifier thresholds, a season results table, a QR token or signing-key record for rotating entrance codes, and the append-only `game_event` table that feeds notifications (7.2.1).

### 5.2 Constraints

- `CHECK (steps_scored BETWEEN 1 AND 2000)`
- `CHECK (ascent_m BETWEEN 2.0 AND 120.0)`
- `CHECK (stair_prob BETWEEN 0 AND 1)`
- `UNIQUE (device_id, id)` on segments, so uploads are idempotent
- Foreign keys from user-owned tables use `ON DELETE CASCADE`, so GDPR account deletion is a single statement.

### 5.3 Indexes and the queries they serve

| Index | Query it supports |
|---|---|
| `climb_segment (building_id, started_at DESC) WHERE status = 'verified'` (partial, per partition) | Recompute a building's owner from the last 7 days of verified climbs. |
| `climb_segment (user_id, started_at DESC)` | Personal history screen; per-user rate checks ("more than 600 steps in 10 minutes?"). |
| `building USING GIST (footprint)` | Geofence check-in: `ST_Contains(footprint, ST_SetSRID(ST_MakePoint(lon, lat), 4326))` or `ST_DWithin` with a 30 m tolerance. |
| PK `team_building_score (season_id, building_id, team_id)` | Increment a team's score (`INSERT ... ON CONFLICT DO UPDATE`). |
| PK `building_claim (season_id, building_id)` | Read or lock the current owner; render building standings in one query. |
| `fraud_flag (created_at) WHERE resolved_at IS NULL` | Moderation queue in the admin panel. |
| `refresh_token (token_hash)` unique | Constant-time lookup on refresh; reuse detection by family. |
| `season USING GIST (active_during)` (from the exclusion constraint) | "Which season is active now?" |

### 5.4 Partitioning, transactions, migrations, backups

- `climb_segment` is range-partitioned by month on `started_at`. Season queries touch one or two partitions. Raw climb data older than 12 months is removed by dropping a partition, not by a slow `DELETE`.
- Accepting a verified segment runs in one transaction (see 3.1). The row lock on `building_claim` serialises concurrent climbs in the same building, so two teams cannot both "win" a race. Climbs in different buildings run in parallel.
- Migrations use Alembic. Autogenerated revisions are reviewed by hand. Partition creation for the next month is a scheduled migration-style job. CI applies all revisions to an empty database and runs `alembic check` to detect drift.
- Migrations follow expand, migrate, contract (see 7.7).
- Backups use pgBackRest with point-in-time recovery (see 7.7). Before a season ends, take a manual `pgbackrest backup --type=full`, because season results are the data users care about most.

---

## 6. API contract

All endpoints are under `/v1`. The canonical definition lives in `/contracts/openapi.yaml`. Both members must approve changes to it.

PDF-defined: `POST /v1/segments`, `GET /v1/buildings/{id}/standings` (was `/floors`, changed to building standings: see the adapted rules in section 2), `POST /v1/checkins`, `GET /v1/me/season-stats`. Everything else is ours.

| Endpoint | Purpose | Notes |
|---|---|---|
| `POST /v1/auth/otp` | Send a 6-digit code to a university e-mail address | Domain allow-list; rate limited |
| `POST /v1/auth/verify` | Exchange e-mail + code for tokens | Max 5 attempts |
| `POST /v1/auth/refresh` | Rotate refresh token | Reuse revokes the family |
| `GET /v1/teams`, `POST /v1/seasons/{id}/join` | List teams, pick one for the season | One team per user per season |
| `POST /v1/checkins` | Check in by signed QR token or geofence | Server verifies HMAC and time window; creates 90-minute range |
| `POST /v1/segments` | Upload a batch of segments | Idempotent; header `Idempotency-Key`; response `{accepted, rejected, flips}` |
| `GET /v1/buildings` | Buildings list | |
| `GET /v1/buildings/{id}/standings` | Team standings and current owner for the building in the active season | One query |
| `GET /v1/leaderboards` | Individual, team, building | Served from Valkey sorted sets |
| `GET /v1/me/season-stats` | Personal stats, landmarks progress, share-card data | |
| `GET /v1/me/segments` | Personal history | |
| `GET /v1/me/events` | Game events for the player's team after a given id | Notification fallback and WebSocket replay (7.2.1); ordered by id, paged |
| `POST /v1/landing-scans` | Barometer-less fallback scan on a stair landing | Strict rate limit |
| `GET /v1/config` | Classifier thresholds (versioned) | Revert in seconds without a deploy |
| `GET /v1/me/export`, `DELETE /v1/me` | GDPR export and delete | Delete cascades |
| `WS /v1/ws` | Live events | Authenticated on connect |

WebSocket events (ours): `building_flipped {building_id, from_team, to_team, at}`, `season_state {paused, ends_at}`.

Segment upload body (one item, ours):

```json
{
  "id": "client-uuid",
  "checkin_id": "uuid",
  "started_at": "2026-11-02T10:14:03Z",
  "building_id": 4,
  "ascent_m": 9.7,
  "duration_s": 22,
  "vert_speed_mps": 0.44,
  "steps": 58,
  "stair_prob": 0.93,
  "classifier_version": "rules-1"
}
```

Raw pressure or step streams never appear in any request.

Error handling rules (PDF): explicit timeouts (connect 10 s, read 20 s). Never retry 4xx. Retry 5xx and network errors with exponential backoff and jitter. A duplicate UUID is treated as success.

---

## 7. Infrastructure and operations

Shared operating model (PDF, host changed by us from Oracle to Azure): one team-managed Linux VM running containers behind a reverse proxy, a custom API, a self-hosted PostgreSQL database, and a CI/CD pipeline the team writes.

### 7.1 Host and hardening

- One Azure VM (see 7.2) in an EU region (GDPR data residency), Ubuntu 24.04 LTS, starting at 2 vCPU and 4 to 8 GB RAM. The PDF used an Oracle Always Free VM; the compose files are identical on any host, including a university VM.
- Tested backups make a rebuild routine, so a lost or replaced VM is a restore, not a crisis.
- SSH keys only, no root login, a dedicated deploy user whose key is restricted to a forced `deploy.sh` command.
- Cloud firewall (security group or NSG) plus `ufw`: 80/443 public, 22 from team IPs only. `unattended-upgrades` for security patches. `fail2ban` on SSH.
- Docker Engine and Compose v2. Four networks: `edge` (only Caddy), `app` (API and workers), `data` (Postgres and Valkey, `internal: true`, no route to the internet), `monitoring` (exporters). Staging runs as a separate compose project on the same host with its own database.
- Encryption at rest: database and data live on a separate encrypted cloud disk (Azure managed disk with platform-managed or customer keys). The PDF used LUKS because the host was a bare VM; the cloud disk encryption replaces it. Backups are encrypted independently.

Containers: `caddy`, `api` (two replicas), `worker` (Celery), `scheduler` (Celery beat), `admin` (SQLAdmin), `postgres`, `valkey`, plus the monitoring stack (Prometheus, Grafana, Loki, Alloy, Alertmanager, node_exporter, cAdvisor, postgres_exporter). Only Caddy publishes ports. The admin panel is reachable only from team IPs (Caddy `remote_ip` matcher) and also requires an admin role in the JWT. Grafana is published through Caddy behind an IP allowlist plus basic auth.

### 7.2 Cloud provider: Azure (decided)

Decision: Azure for the VM and supporting infrastructure. Notifications use our own channel (7.2.1); no Firebase. Everything runs as Docker Compose on one Azure VM, so the app is not tied to Azure and could move to another host with a restore from backup.

Rule carried over from the PDF: no managed backend platforms (no Firebase database or auth, Supabase, Entra External ID, App Service-style PaaS). We use Azure for infrastructure primitives only. If the course rules differ, check with the professor before using any managed database or cache.

| Need | Azure service | Notes |
|---|---|---|
| Production VM | Azure VM, B-series (x86), Ubuntu 24.04, 2 vCPU, 4 to 8 GB RAM | Size up only if Postgres or Grafana need it. ARM (`Dpsv5`) works too if the credit covers it; images build multi-arch. |
| Data disk | Managed disk, separate from the OS disk, encryption at rest | Replaces the PDF's LUKS. |
| Firewall | Network security group: 80/443 public, 22 from team IPs only | Same rule set as `ufw` on the host. |
| Off-site backups | Blob Storage account in a second EU region, versioning on | pgBackRest has a native Azure repository type. |
| Sign-in e-mails | Azure Communication Services Email (or an SMTP relay as fallback) | One-time codes only. |
| Budget control | Cost Management budget with alerts | Create it before any other resource. |
| Staging | Same VM with a separate compose project, or a second small VM | |
| Uptime check | Application Insights availability test, or Uptime Kuma elsewhere | Must live outside the VM it watches. |
| DNS | Azure DNS (optional), or the registrar's DNS | |
| Credit | Azure for Students: USD 100, no credit card, via GitHub Student Developer Pack (verify current terms) | |

Not used: Notification Hubs and FCM (own notification channel, see 7.2.1), Key Vault (SOPS and age cover secrets), managed PostgreSQL, managed Redis, App Service, Container Apps, AKS, Functions, Cosmos DB.

Operating rules:

- Create the budget alert first, at a low threshold. Cloud bills do not stop on their own.
- Use an EU region (GDPR data residency).
- Delete anything unused: idle VMs, extra disks, public IPs, old snapshots.
- Write the monthly estimate in `/docs/cost.md` after Week 1.

Other tools (provider independent):

| Need | Choice | Notes |
|---|---|---|
| Domain | Free one-year domain from the GitHub Student Developer Pack, or a cheap domain | Claim it only when the project starts; the year begins at redemption. |
| TLS | Let's Encrypt via Caddy | |
| CI/CD and registry | GitHub Actions, GHCR (GitHub Pro via Student Pack) | Build multi-arch: `docker buildx --platform linux/amd64,linux/arm64`. |
| Monitoring | Prometheus, Grafana, Loki, Alertmanager (self-hosted) | |
| Dev tools | Android Studio, VS Code, JetBrains (student licence), GitHub Codespaces | |
| App distribution | APK on GitHub Releases | Avoids store fees. Google Play is a one-time USD 25 and optional. |

Running cost: the student credit should cover the course. The PDF assumed EUR 0 on an Oracle free VM; that no longer holds. After the credit ends, a small VM plus a bucket should stay in the low tens of EUR per month (verify with the Azure calculator).

Why Valkey and not Redis: Redis left its BSD licence in 2024. Valkey is the Linux Foundation's BSD fork with the same protocol, so Celery and the client libraries work unchanged.

### 7.2.1 Notifications without Firebase: our own channel (decided 2026-10-29)

Course rule (professor, 2026-10-29): no Firebase and no similar managed platforms. We do not use FCM, Firebase in any form, OneSignal, Pusher, Expo push, AWS SNS or Azure Notification Hubs (the managed ones also deliver through FCM on Android). Notifications are delivered by our own code over our own server.

How it works:

1. Every event a player should hear about (`building_flipped`, `season_state`) is written as a row of the append-only `game_event` table (id is a `bigint` identity, so ids only grow) in the same transaction that changes the claim. After commit the API publishes it on Valkey, so both API replicas see it.
2. While a play session runs, the Kotlin foreground service that already does the sensing (section 4.3) keeps one WebSocket open to `WS /v1/ws`, authenticated on connect. On connect it sends the last event id it has seen (`since`); the server first replays the missed events for the player's team, then streams new ones. Delivery is at least once: the app ignores ids it has already handled.
3. When the player's team loses a building, the service posts a local Android notification ("AC took the Politehnica building"). Tapping it opens that building's screen. The service does this itself, so it works with the JS runtime closed.
4. Connection handling: a ping every 30 s, reconnect with exponential backoff and jitter, close the socket when the session stops.
5. Fallback when no session runs: a WorkManager job (every 15 minutes, the Android minimum; Doze can stretch it) calls `GET /v1/me/events?since=<id>` and shows the same notifications.
6. The game screens use the same WebSocket while the app is open (Week 4 hook).

Details:

- Message content: short text plus `building_id`, no personal data beyond the team code and the building.
- Rate limit notifications per user (for example at most one per building per 10 minutes) so a flip war does not spam players.
- Known limit: with no session running and the phone in deep Doze, a notification can arrive late (at the next WorkManager window). We accept this and measure it.
- Evaluation (section 11): notification delay (event to notification) with the service on and off, and the battery cost of the open socket, on both phones.
- Considered and not chosen: UnifiedPush with a self-hosted ntfy server (real-time even without a session, but every tester must install a second app as the "distributor").

### 7.3 Container builds

Every service image is built in two stages: a builder with compilers and dev dependencies, and a minimal runtime stage running as a non-root user, with a read-only root filesystem where possible. The PDF's example used Django; this is the same shape adapted to FastAPI (ours):

```dockerfile
FROM python:3.13-slim AS builder
RUN pip install uv
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime
RUN useradd --uid 10001 app
COPY --from=builder /src /app
ENV PATH="/app/.venv/bin:$PATH"
USER app
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 7.4 Reverse proxy

Caddy 2 terminates TLS with auto-renewed Let's Encrypt certificates, sets HSTS and security headers, applies per-IP request limits, and load-balances across the two API replicas with active health checks. Nginx with certbot is an acceptable equivalent.

### 7.5 Secrets and configuration

Twelve-factor configuration. Secrets (database passwords, JWT signing keys, SMTP credentials, QR HMAC key) are stored encrypted in the repo with SOPS and age. The age private key exists only on the server (mode 0400, root-owned) and in a sealed team password-manager entry. `deploy.sh` decrypts to `/run/secrets`, which Compose mounts through `secrets:`, so secrets never show in `docker inspect` or CI logs. CI holds only the SSH deploy key and a GHCR token, scoped narrowly. JWT signing keys rotate each semester, keeping the previous public key for validation during the overlap.

### 7.6 CI/CD (GitHub Actions)

- Every pull request: linting (ruff and mypy for Python, ktlint for Kotlin, ESLint and `tsc` for the app), unit tests, integration tests against a real PostgreSQL service container. Migrations are applied to an empty database and checked for drift (`alembic check`). Plus the trace-replay gate: recorded sensor traces run through the segmenter and the server rules, and precision must stay above a set threshold.
- Merge to `main`: build multi-stage images, scan with Trivy (fail on high or critical CVEs that have a fix), tag by git SHA, push to GHCR, deploy to staging automatically.
- Promotion to production: manual approval on a protected GitHub Environment runs `deploy.sh <sha>` over SSH. The script records the running tag, runs expand-only migrations, runs `docker compose up -d --wait`, and waits for health checks. If they fail within 90 seconds, it re-pins the previous tag automatically.
- Rollback: `deploy.sh rollback` re-pins the tag recorded in `/srv/floorwars/last_good`. Expand-only migrations guarantee the old image still works. Classifier thresholds live in the database `config` table, versioned, so a bad threshold change reverts in seconds without a deploy.
- Mobile builds: a separate workflow builds signed release APKs (keystore as an encrypted secret) and attaches them to GitHub Releases. Play internal track is optional.
- The Android sensor pipeline has unit tests that feed recorded pressure and step traces through the segmenter, so detection quality is a CI gate.

### 7.7 Database operations

- Schema changes follow expand, migrate, contract: add new columns or tables first (backward compatible), deploy code that writes both shapes, backfill, drop the old shape in a later release. Add new constraints `NOT VALID` and validate separately so large tables are not locked. Rolling back the application never needs a schema rollback.
- Backups: pgBackRest, weekly full plus daily differential, plus continuous WAL archiving (`archive_timeout = 60s`) for point-in-time recovery. Repository off-site (Azure Blob Storage in a second region, using pgBackRest's Azure repository type; or a teammate or lab machine over SFTP), AES256 encrypted, keeping two to four fulls depending on space.
- Recovery targets: RPO at most 5 minutes, RTO under one hour.
- Monthly restore drill: restore the latest backup into a throw-away container, run row-count and checksum queries, record the result in the ops log. A backup that has never been restored counts as not existing.
- Least-privilege roles: the app role cannot run DDL. Migrations use a separate role.

### 7.8 Observability

- Prometheus scrapes node_exporter, cAdvisor, postgres_exporter and the app `/metrics` endpoint (request rate, error rate, latency histograms, queue depth).
- Grafana dashboards cover the four golden signals per service. Logs are structured JSON, shipped by Grafana Alloy to Loki.
- FloorWars custom metrics: segments accepted vs rejected, detection latency (segment `started_at` to server accept), fraud flags by rule, WebSocket connections, active users, sessions with gaps.
- Alertmanager notifies a team Discord channel when: API error rate above 2% for 5 minutes, p95 latency above 500 ms, disk above 80%, a backup older than 26 hours, a certificate expiring within 14 days.
- External uptime check: Uptime Kuma on a teammate's Raspberry Pi or a second tiny VPS. It catches the case where the whole server is down, which internal monitoring cannot see.

### 7.9 Authentication pattern

The team implements authentication; libraries are used only for cryptographic primitives.

- Sign-in with e-mail one-time codes: 6 digits, 10-minute expiry, stored hashed, five attempts maximum. No passwords. (If passwords are ever added: Argon2id.)
- Access tokens: JWT, 15 minutes, signed with EdDSA or ES256, carrying `sub`, `exp`, `aud` and a `kid` for key rotation.
- Refresh tokens: opaque 256-bit values stored server-side as SHA256 hashes. They rotate on every use. Presenting an already-used token revokes the whole family, which detects theft.
- Client storage (ours): `react-native-keychain` backed by the Android Keystore. The PDF suggested Tink AEAD over DataStore for native Kotlin.

### 7.10 Mobile network-failure strategy

- Every write goes into a local outbox (Room/SQLite) with a client-generated UUID that doubles as the idempotency key.
- A background sync job (WorkManager) retries with exponential backoff and jitter, on unmetered or validated networks where appropriate.
- The server treats duplicate UUIDs as success (`INSERT ... ON CONFLICT DO NOTHING`), so a retry after a lost response never double-counts.
- Reads are cached with a timestamp and shown with a "last updated" label when offline.
- Timeouts are explicit (connect 10 s, read 20 s). 4xx is never retried; 5xx and network errors are.

### 7.11 Security checklist

Input validation at the API boundary (Pydantic v2 strict). Parameterised SQL only. Rate limiting at two layers (Caddy per IP, plus a Valkey token bucket per user and endpoint). CORS limited to the team's own web origins. Dependency scanning in CI. Least-privilege database roles. GDPR basics: privacy notice, data export and account deletion endpoints, documented retention periods.

---

## 8. Security and privacy

- Data minimisation: raw sensor streams never leave the phone. Only per-segment features (ascent, duration, steps, vertical speed, classifier score) are uploaded. Location is used only at check-in, never tracked continuously.
- Encryption: TLS 1.3 in transit; LUKS-encrypted database volume; encrypted pgBackRest repository; tokens in the Android Keystore.
- Input validation: Pydantic strict models with bounded numeric ranges. Server-side plausibility rules mirror the client rules. Signed, expiring QR tokens prevent photographed codes from being reused remotely.
- Rate limiting: Caddy per-IP limits; a Valkey token bucket per user (at most 60 segment uploads per hour and 600 verified steps per 10 minutes).
- Health-adjacent data: activity data is personal data under GDPR. The privacy notice states purpose. Raw segments are kept for 12 months. Users can export or delete everything. Users under 18 are not accepted.
- Safety by design: points never reward speed, only verified stair steps with a matching pressure change, with diminishing returns per hour, so the game never encourages running on stairs.
- Admin panel: team IPs only plus admin role in the JWT.
- Aggregated insights (future B2B): building-level only, published when at least 20 users contribute, never individual data.

---

## 9. Team split and working rules

| | **Cristea (Member A): Sensing and Mobile Core** | **Ionut (Member B): Backend, Infra and Game UI** |
|---|---|---|
| Owns | RN app skeleton, Kotlin native module, foreground service, segmenter and classifier, Room outbox, sync, auth/check-in/fallback screens, privacy screens, evaluation | FastAPI, DB schema and migrations, scoring and claim transaction, Valkey, WebSocket, Celery/push, cloud setup, admin panel, deployment, monitoring, plus the game-facing RN screens (building standings, leaderboards) |
| Hardest risk | Reliable background sensing and classifier accuracy | Race-free claim transaction and operating the deployment |
| Delivers to the other | App shell, sync client, labelled traces | Stable OpenAPI contract, staging URL, WS events |

Why this split: Cristea carries the hardest mobile-systems work (native code, sensors, data labelling). Ionut carries all server and ops work and takes the game screens on the RN side so the mobile UI load is not all on Cristea.

### 9.1 Repository layout

```
/app              React Native app (Cristea). Ionut owns /app/src/features/{building,leaderboard}
/app/android      Kotlin native module and service (Cristea)
/server           FastAPI, Alembic, Celery (Ionut)
/infra            compose files, Caddy, monitoring, deploy.sh (Ionut)
/contracts        openapi.yaml, WebSocket event schemas (shared)
/traces           labelled sensor traces and labels.csv (Cristea), used by Kotlin tests and server tests
/docs             evaluation.md, runbook.md, devices.md, privacy notice, report material
```

### 9.2 Working rules

- Contract first. Week 1 ends with a reviewed `openapi.yaml`. Cristea generates the TS client from it; Ionut implements against it. Contract changes are PRs that touch `openapi.yaml`, reviewed by the other member.
- One branch per feature, PR into `main`, the other member reviews, CI green before merge.
- Two 20-minute syncs a week: Monday plan, Thursday integration. Friday: tag a demoable build.
- Each member can unblock the other with fakes. Ionut owns a fake-segment script that posts valid segments without a phone and ships it in Week 1. Cristea runs a mock server generated from the OpenAPI file (for example Prism) for UI work.
- Cristea hands over a runnable app shell (navigation, generated API client, auth stub) by the end of Week 1, so Ionut's screens are never blocked on it.
- CI checks that the server responses match `openapi.yaml` (contract tests), so the mock and the real server cannot drift apart silently.

### 9.3 Integration points

About 85% of the work is independent. These are the moments that need both of you. Everything else runs in parallel against fakes.

| When | What | Who | Done when |
|---|---|---|---|
| Week 1, first 2 days | Review and freeze `openapi.yaml` and WS event schemas | Both | PR merged with both approvals |
| Week 1, end | App shell and API client handed over; fake-segment script shipped; cloud provider chosen | Cristea, Ionut, both | Ionut runs the shell; Cristea posts a segment with the script |
| Week 2 | Staging URL live, so Cristea can switch from the mock to the real server | Ionut, then Cristea | Sign-in works on a phone against staging |
| Week 3, Wednesday | First real end-to-end test: one real climb through the real service, API and database | Both | A real climb appears as `verified` and the building owner changes; ugly is fine |
| Week 4 | Notifications (event feed and replay on the server, socket and local notification in the Kotlin service, tap to open) | Pair | Phone 2 gets a notification when phone 1 flips a building |
| Any week | Contract change | Author, then the other reviews | `openapi.yaml` PR approved |
| Weeks 5 and 6 | Threshold tuning loop: Cristea's trace results to Ionut's config table | Both | New thresholds live through `GET /v1/config` without a deploy |

Dependency risks to watch: a fake only behaves like the spec, so real code may differ at integration time. The contract tests above and the Week 3 Wednesday check exist to catch that early. Server plausibility thresholds are guesses until Cristea's tuning produces real numbers.
- Test devices: at least 2 Android phones with a barometer. Record exact models in `/docs/devices.md`.
- Docs rule: if you add an endpoint, table, env var or threshold, update this file or `/contracts` in the same PR.

---

## 10. Six-week plan

Scope for 6 weeks (ours): the full climb-to-claim loop, live map, push, admin panel, share cards, fallback, monitoring, pilot, evaluation. Raids, achievements, iOS, LiteRT and corporate mode are cut unless every Week 5 exit criterion is green early.

### Week 1: Foundations and contract

Goal: both sides can build and run; contract frozen; first sensor traces recorded.

**Cristea**
- Init RN (TypeScript) app: navigation shell (Auth and Main), lint, prettier, Jest, pre-commit hooks. Pin the RN version. By the end of the week: generate the TS API client from `openapi.yaml`, wire an auth stub, and hand Ionut a runnable shell.
- Kotlin module `FloorSensors` skeleton: `startLogging(label)`, `stopLogging()`, event emitter, permission requests (`ACTIVITY_RECOGNITION`, notifications, `FOREGROUND_SERVICE_HEALTH`).
- Foreground service (type `health`) with persistent notification, registering `TYPE_PRESSURE` and `TYPE_STEP_DETECTOR`.
- Sensor logger screen: record labelled traces (`stairs_up`, `stairs_down`, `elevator_up`, `walk_flat`, `shake`, `blow`, plus placement `pocket`, `hand`, `bag`). Save as CSV or JSON with device model, `has_barometer`, timestamps. Export through the share sheet.
- Record at least 20 labelled traces in a faculty building on 2 devices. Commit them to `/traces` with `labels.csv`.
- Write `/docs/devices.md`.

**Ionut**
- Scaffold `/server` and `/infra`. Review the ER model in section 5.
- Alembic baseline: `user`, `device`, `team`, `season` (tstzrange plus exclusion constraint), `team_membership`, `building` (PostGIS polygon, GiST), `refresh_token`.
- Write `openapi.yaml` for all endpoints in section 6 and the WebSocket event schema. Review with Cristea.
- FastAPI skeleton: `/healthz`, config, structured JSON logging.
- GitHub Actions: lint and pytest on PR, multi-stage multi-arch (amd64 and arm64) Docker build, push to GHCR.
- Set up the Azure budget alert first (7.2), then provision the VM, encrypted data disk and firewall rules, and harden it (7.1). Docker Compose with Caddy and TLS. Domain.
- Ship the fake-segment script (posts valid segments with no phone) and a Prism mock config for Cristea.
- ~~Create the Firebase project for FCM~~ Dropped on 2026-10-29: the course does not allow Firebase. Notifications use our own channel (7.2.1).

Exit: `/healthz` answers over HTTPS; `openapi.yaml` merged; the app installs on both phones; at least 20 labelled traces in the repo.

### Week 2: Auth, check-in, detection algorithm

Goal: a user can sign in and check in; the segmenter detects climbs offline on recorded traces.

**Cristea**
- Segmenter v1 in Kotlin (pure, no Android imports): pressure low-pass or median smoothing, ascent-window detection (seconds to minutes), features `ascent_m`, `duration`, `vert_speed_mps`, `steps`, `steps_per_m`, and the pressure-steps match flag.
- Rules classifier v1 (stairs, elevator, other) using the starting thresholds in 3.3. Reject shake and blow patterns.
- JUnit trace-replay harness over `/traces` that prints a confusion matrix. Put baseline numbers in `/docs/evaluation.md`.
- Auth screens: e-mail, OTP entry, team choice. Keystore token storage, refresh interceptor with rotating refresh token. Generated TS API client wired in.
- Check-in screen: QR scanner and the one-shot geolocation path.

**Ionut**
- Auth: e-mail OTP (domain allow-list, 10-minute expiry, 5 attempts, hashed codes), JWT access plus rotating refresh with family reuse detection, device registration, age and terms confirmation.
- Team and season endpoints; join once per season.
- `POST /v1/checkins`: verify the HMAC-signed rotating QR token and its window; geofence path with `ST_Contains` / `ST_DWithin` 30 m; insert the check-in with a 90-minute range.
- Script that generates printable entrance QR codes.
- Seed data: 2 real buildings (footprints only), 4 to 5 teams, one active season.
- Tests: auth flow, OTP abuse, token reuse, check-in valid, expired and forged.
- Staging deploy from `main` (GHCR pull, `deploy.sh`), SOPS and age secrets to `/run/secrets`.

Exit: on a real phone: sign up, pick team, scan entrance QR, see "Checked in: Building X, 89 min left". The segmenter produces a confusion matrix on the traces.

### Week 3: Core pipeline, background service, claims (critical path)

Goal: a real stair climb in a building becomes points on the server.

**Cristea**
- Wire the segmenter into the live service: real sensor events, wake-lock strategy, sampling rate selection (10 to 25 Hz), batching to save battery.
- Native Room/SQLite outbox: segments with client UUID, status, check-in id, `has_barometer`. Module API `getPending(limit)` and `markSynced(ids)`.
- Attribute segments to the building of the active check-in.
- JS sync worker: batched `POST /v1/segments` with `Idempotency-Key`, exponential backoff with jitter, per-segment accepted or rejected handling. Triggered by WorkManager or background-fetch and on app foreground.
- Status screen: service running, last segment, pending count, battery-optimisation hint.
- Verify the service survives screen-off and app swipe-away on both phones. Log a "sessions with gaps" metric.

**Ionut**
- Migrations: `climb_segment` (monthly range partitions, `UNIQUE(device_id, id)`, CHECKs), `fraud_flag`, `team_building_score`, `building_claim`, the indexes in 5.3, the next-month partition job.
- `POST /v1/segments`: Pydantic strict batch; server plausibility rules (speed, cadence, steps/m, pressure-steps match, per-user rate); status `verified` or `rejected`; `fraud_flag` for rejects.
- Claim transaction as in 3.1, with a concurrency test (parallel climbs in one building).
- Scoring: points per verified stair step with diminishing returns per hour.
- Valkey: `ZINCRBY` leaderboards, `PUBLISH building_flipped`, token bucket (60 uploads/hour, 600 verified steps/10 minutes).
- `GET /v1/buildings/{id}/standings` (owner and team standings in one query) and `GET /v1/leaderboards`.
- Fake-segment script. Replay `/traces` through the server plausibility rules as a pytest case.

Wednesday check: run one real climb through the real service, API and database as early in the week as possible, even if it is ugly. Surprises (field names, time zones, auth edges) surface here.

Exit: walk up real stairs with the phone in a pocket; the segment lands in the DB as `verified`; team score and `building_claim` update; a duplicate upload is a no-op.

### Week 4: Live game UI, push, anti-cheat

Goal: the loop is visible and social.

**Cristea**
- WebSocket connection manager (auth, reconnect, resume) exposed as a hook for Ionut's screens.
- Home screen: current check-in, today's stair steps and metres, pending-sync indicator.
- Personal history screen with the reason for each rejected segment.
- Barometer-less fallback: detect `has_barometer=false`, QR-sticker-on-landing flow ("scan at the stairs of building X") with local rate limit.
- Onboarding: safety copy (no running), permission explanations, per-manufacturer battery-optimisation guide.
- Classifier tuning pass 1 with new real-world traces (pocket, bag, hand, going down, flat walking). Record new precision and recall.

**Ionut**
- Building standings screen (`react-native-svg`): team shares in team colours from `GET /v1/buildings/{id}/standings`, live updates from `building_flipped`, Reanimated colour-flip animation.
- Leaderboards screen: individual, team, building tabs; season selector.
- WebSocket hub in the API: auth on connect, Valkey pub/sub fan-out so two replicas share events.
- Notifications (7.2.1): `game_event` table written in the claim transaction, replay of missed events on WebSocket connect (`since`), `GET /v1/me/events`, per-user notification rate limit. Pair with Cristea on the socket in the Kotlin service, the local notification and the tap that deep-links to the building screen.
- Landmarks progress (Eiffel Tower style conversion) in `GET /v1/me/season-stats`.
- `POST /v1/landing-scans` with strict rate limits.
- Anti-cheat v2: per-device limits, repeated identical segment detection, impossible-sequence checks (climbs in two buildings too close in time), fraud flag reasons.

Exit: two phones on different teams: phone 1 climbs, phone 2's building standings flip live and phone 2 gets a notification. The barometer-less path works on a device or an emulator flag.

### Week 5: Admin, share cards, monitoring, operability

Goal: feature complete and operable.

**Cristea**
- Share cards (9:16): building standings, personal stats, "building flipped" moment. Rendered with `react-native-view-shot`, sent via the Android share sheet. Ionut provides the standings component.
- Season results screen and a "season paused" banner when the server switch is on.
- Offline and error states everywhere: no network, expired token, 5xx, camera denied, missing sensor.
- Accessible contribution mode behind a flag and non-shaming elevator wording (agree rules with Ionut).
- GDPR: in-app privacy notice, export my data, delete my account, under-18 gate.
- Battery measurement: drain per hour over 3 hours, service on vs off, on both devices. Record in `/docs/evaluation.md`.
- Classifier tuning pass 2. Thresholds move into a structure that the server `config` table can override via `GET /v1/config`.

**Ionut**
- Admin panel (SQLAdmin, IP-allowlisted through Caddy `remote_ip`, admin JWT role): edit building footprints (GeoJSON), create seasons, assign teams, review and resolve fraud flags, "season paused" switch.
- Versioned classifier-threshold `config` table and `GET /v1/config`.
- Season close transaction with results snapshot. Celery scheduled jobs: season rollover, partition creation, digests.
- `GET /v1/me/export` and `DELETE /v1/me` (cascade). Retention job that drops partitions older than 12 months.
- Caddy rate limits. Security review: CORS, validation bounds, secrets, dependency scan, Trivy gate.
- Monitoring: Prometheus, Grafana, Loki + Alloy, Alertmanager to Discord, the custom metrics in 7.8, and one Grafana dashboard for the demo.
- pgBackRest to the off-site target and one restore drill. `deploy.sh rollback` rehearsal. `docs/runbook.md`.
- k6 load test on `POST /v1/segments` and WebSocket.

Exit: an admin can create a season and a building from the panel without SQL; Grafana shows live metrics; a share card exports from a real session; one backup restore proven.

### Week 6: Pilot, evaluation, final demo

Goal: real data from real users; numbers for the report; frozen release.

**Both**
- Pilot with 15 to 30 students in 1 or 2 buildings (the PDF targeted 30 to 50 in 2 buildings; scale to what we can recruit). Distribute the APK through GitHub Releases, run an onboarding session, open a WhatsApp or Discord group, run a short "Faculty Wars Week" mini-season.
- Daily triage: crashes, fraud flags, sessions with gaps, battery-kill reports per phone maker.
- Bug-fix freeze at mid-week. Signed release build, tagged `v1.0`.
- Final report and presentation (outline in section 14).

**Cristea**
- Pilot ground truth: a short in-app "was this a stair climb?" prompt on a sample, plus labelled walks with volunteers.
- Evaluation: precision, recall and F1 per class, per device model, per placement; barometer coverage; battery cost; sessions-with-gaps rate. Write `/docs/evaluation.md` with the confusion matrix and charts.
- Final threshold tuning with Ionut through the config table. Re-run all traces in CI.
- Signed release APK, crash-free check, UX polish.
- Demo script: check in, climb, faculty colour takes the building, rival gets a notification.

**Ionut**
- Pilot operations: watch Grafana and Alertmanager, fix server issues, tune plausibility rules from real fraud flags.
- Metrics queries for the report: users, climbs, stair steps, flips per building, accepted vs rejected, WebSocket uptime.
- Freeze production, verify backups, rehearse `deploy.sh rollback`.
- Live Grafana dashboards and a wall-screen view of the building standings for the demo.
- Report sections: architecture, DB design, deployment, security and privacy, monitoring.
- Rehearse the demo twice with a failure plan (pre-recorded video, local fallback server).

Exit: signed APK on GitHub Releases; evaluation report with precision and recall; live dashboard; demo rehearsed.

### Summary table

| Week | Cristea | Ionut | Integration gate |
|---|---|---|---|
| 1 | RN shell, native sensor logger, first traces | Schema v1, OpenAPI, CI, VM and TLS | `/healthz` over HTTPS; contract merged |
| 2 | Segmenter v1, replay harness, auth and check-in UI | Auth, check-in, seed data, staging deploy | Sign up, then check in on a device |
| 3 | Live service, outbox, sync | Segments API, plausibility, claim transaction, Valkey | Real climb becomes a verified claim |
| 4 | WS manager, history, fallback, tuning 1 | Building standings and leaderboards UI, WS hub, event feed and notifications, anti-cheat v2 | Two phones: live flip and notification |
| 5 | Share cards, GDPR UI, offline states, battery tests | Admin panel, config table, monitoring, backups, k6 | Feature complete, operable |
| 6 | Pilot ground truth, evaluation, release APK | Pilot ops, metrics, freeze, demo infra | Pilot done, final demo |

---

## 11. Evaluation plan

The project produces measurable results rather than screenshots. These numbers go in the final report.

| Metric | How | Owner |
|---|---|---|
| Classifier precision, recall, F1 per class (stairs, elevator, other) | Hand-labelled traces and pilot ground truth; confusion matrix | Cristea |
| Same, split by device model and by phone placement | Same data, grouped | Cristea |
| Barometer coverage | Share of pilot devices with `has_barometer = true` | Cristea |
| Battery cost per hour | 3-hour runs with service on vs off on both test phones | Cristea |
| Sessions with gaps | Fraction of check-in windows where the service was killed | Cristea |
| Upload latency | Segment `started_at` to server accept | Ionut |
| Accepted vs rejected segments, fraud flags by rule | Prometheus counters and `fraud_flag` | Ionut |
| Flips per building, active users, climbs | Report queries | Ionut |
| API load behaviour | k6 results | Ionut |
| Backup restore | Restore drill log | Ionut |

CI gate: the trace-replay suite fails the build if precision drops below the agreed threshold. Set the threshold after the first baseline in Week 2.

---

## 12. Risks and mitigations

| Type | Risk | Mitigation |
|---|---|---|
| Technical | Budget phones lack a barometer. | QR-landing fallback; record `has_barometer` per device and report coverage. |
| Technical | Phone-maker battery optimisers kill background services. | Foreground service with persistent notification; in-app guide per manufacturer; a "sessions with gaps" metric. |
| Technical | Pressure noise from doors, HVAC or stairwell wind. | Short windows, smoothing, the requirement that ascent correlates with steps; tune on pilot data. |
| Technical (RN) | RN JS runtime is killed in the background. | Sensing, segmentation and the outbox live in the Kotlin service. JS only consumes. |
| Technical (RN) | Kotlin is a bigger share than planned. | Keep the module API small. Cristea owns it. |
| Technical (RN) | RN upgrade friction with native code. | Pin the version in Week 1; no upgrades. |
| Schedule | Week 3 is the critical path (service plus claim transaction). | Both build against `/traces` and the fake-segment script so neither blocks. |
| Schedule | Scope creep. | Raids, achievements, iOS, LiteRT only after the Week 5 exit is green. |
| Operational | Server down during exams or holidays. | Alertmanager to Discord, external uptime check, on-call rota with a runbook, tested restores, "season paused" switch. |
| Market | Novelty fades after week one. | Short seasons, raids (stretch), captains, the B2B pivot, which does not depend on viral growth. |
| Privacy | Activity and location data could profile students. | Minimisation, no continuous GPS, retention limits, export and delete. |
| Ethical | Students with disabilities or injuries are excluded from a stairs-only game. | Accessible contribution mode; wording that never shames elevator use. |
| Ethical / safety | Competition encourages running on stairs. | No speed rewards, hourly caps, safety copy in onboarding. |
| Integrity | Cheating through emulators, modified clients or phones handed to friends. | Server-side plausibility, per-device limits, admin-reviewed fraud flags, Play Integrity as a stretch. |
| Infra | Cloud credit runs out, or a forgotten resource drains it. | Budget alert on day one, `docs/cost.md`, delete unused resources, backups with tested restores so a move to another VM or provider is a restore. |
| Infra | Without Google's push service, notifications reach a phone only while its session runs or at its next poll. | Event feed with replay, so nothing is lost; measure the delay and report it (7.2.1). |

---

## 13. Launch, marketing, monetization

### 13.1 Marketing plan (PDF)

- Platforms: TikTok and Instagram Reels (primary, campus content); Discord or WhatsApp communities per faculty for coordination; r/Romania or r/timisoara for launch posts.
- Launch campaign "Faculty Wars Week": a one-week season at the start of a semester. A live building map runs on a screen in a busy hallway or canteen (with the faculty's permission). Student organisations act as team captains. The faculty holding the most floors at the end wins a sponsored prize (pizza for the year group, or a trophy that physically moves to the winning building). Daily recap reels follow the shifting map.
- Recurring "Building Flip of the Week": a 15-second vertical video. A building standings view animates colour changes over the week, cut with point-of-view stair-climb footage and one statistic ("the building changed hands 11 times"). The standings animation is exported from the app's own UI, so the format costs minutes.
- Hashtags: `#FloorWars`, `#FloorWarsUPT` (one tag per campus), `#TakeTheStairs`.
- Meme formats: "elevator people vs stair people", "POV your faculty just lost the building".
- Each faculty gets a captain role that can call raids (stretch); captains become micro-influencers.

### 13.2 Monetization (PDF, not part of the 6-week build)

| Rank | Model | Price estimate | Who pays | Notes |
|---|---|---|---|---|
| 1 | B2B building challenges (corporate wellness) | EUR 300 to 800 per 4-week challenge, or EUR 1 to 2 per employee per month | HR and well-being managers at large employers | Same product with private leagues; no hardware to install (StepJockey's main friction). Hosting is free, so any deal is margin. |
| 2 | Sponsored seasons on campuses | EUR 200 to 1,000 per season | Sports brands, local gyms, food-delivery or mobility brands | Sponsor logo on the season map and prizes. Exclude brands that conflict with the health message. |
| 3 | Cosmetic in-app purchases | EUR 0.99 to 2.99 | Engaged students | Team banners, building skins, profile frames. Never pay-to-win. |
| 4 | Captain / organiser tier | EUR 2.99 per month | Student organisations, event organisers | Custom events, private brackets, statistics export. |
| 5 | Aggregated facility insights | Bundled with B2B | Facility managers | Building-level stair-use trends only, published when at least 20 users contribute; never individual data. |
| 6 | Ads | n/a | n/a | Not recommended: low revenue at this scale and it erodes the healthy-campus brand. |

Running cost: covered by the student cloud credit during the course (Azure VM, storage, outbound e-mail). After the credit ends, expect a small monthly bill; estimate it in `docs/cost.md` after Week 1. The PDF assumed EUR 0 on an Oracle free VM; that no longer holds. APK distribution through GitHub Releases during the course.

---

## 14. Presentation outline and academic angle

### 14.1 Slide outline (PDF)

| # | Slide | Key message |
|---|---|---|
| 1 | FloorWars: take the stairs, take the building | A campus territory game powered by the barometer already in every phone. |
| 2 | The problem nobody gamified | Stair challenges exist, but they rely on paper logs or NFC hardware; personal floor counters have no social pull. |
| 3 | The insight: one floor is about 0.38 hPa | Phone sensors can tell stairs from elevators with no hardware installed in buildings. |
| 4 | Demo storyboard | Check in, climb, your faculty's colour takes the building, the rival team gets a notification. |
| 5 | Market and competitors | StepJockey, health apps, manual challenges: what each lacks and where FloorWars sits. |
| 6 | Why this is academically solid | Sensor fusion under noise, a measurable classifier (precision and recall on labelled climbs), adversarial anti-cheat, background-execution constraints. A mobile systems problem, not a CRUD app. |
| 7 | Engineering decisions | PostgreSQL 18 + PostGIS, monthly partitions, row locks for claims, pgBackRest PITR; Docker multi-stage builds, Caddy TLS, GitHub Actions, Prometheus and Grafana; rotating refresh tokens. |
| 8 | Architecture and data flow | Phone, outbox, idempotent batch API, transactional claim update, WebSocket broadcast. |
| 9 | Go-to-market and business model | Faculty Wars Week launch; B2B office challenges; infrastructure on Azure student credit, with a cost estimate for after the course. |
| 10 | Plan, risks and evaluation | Milestones, a pilot, and the evaluation metrics we will report. |

### 14.2 Why it works for the course (PDF)

- Technical depth where the course focuses: sensor fusion, signal processing, background execution under Android power management, and on-device classification. Results are measurable (detection precision and recall, battery cost per hour, upload latency).
- Defensible gap: hardware-free verified stair detection plus building-level territories does not exist in the products surveyed. The anti-cheat layer makes it an applied security and data-integrity exercise.
- Real-world relevance: a health intervention with a plausible B2B market, and a campus pilot yields real data that could support a paper or thesis chapter.
- Ranking in the PDF's comparison of five ideas (complexity 3, novelty 5, marketability 4, monetization 3, engineering depth 5). FloorWars won because it combines the highest novelty with moderate build risk and puts the phone's sensors at the centre of the project. Runner-up was ThenAgain (rephotography).

---

## 15. Appendix

### 15.1 Original milestone plan (PDF) and how we compressed it

The PDF planned about 14 teaching weeks for 3 to 4 people, starting 19 October 2026 with a winter-break pause:

| Milestone | Dates | Content |
|---|---|---|
| M1 Foundations | 19 Oct to 1 Nov | ER model, Alembic baseline, auth, health endpoint, Oracle VM (we use an Azure VM), CI, Caddy TLS, sensor logger app |
| M2 Core pipeline | 2 to 15 Nov | `climb_segment` partitioned, scores, claims, seed data for 2 buildings, check-in and segment upload, staging, SOPS, pgBackRest, foreground service, segmenter, classifier v1, outbox and sync |
| M3 Game loop | 16 to 29 Nov | Claim transaction with row locks, fraud flags, leaderboards, WebSocket flips, push, production deploy with manual approval and auto-rollback, monitoring, building standings UI, QR check-in, share cards |
| M4 Hardening | 30 Nov to 13 Dec | First restore drill, EXPLAIN ANALYZE, rate limits, admin panel, export/delete, k6, Trivy, runbook, QR fallback, offline states, battery measurements |
| M5 Pilot | 14 to 20 Dec and 5 to 17 Jan | Season results snapshot, threshold tuning via config table, on-call rota, pilot with 30 to 50 students in 2 buildings, classifier evaluation |
| M6 Final demo | Last teaching week | Final metrics, frozen release, live dashboards, presentation and report |

Our 6 weeks map onto this as: Week 1 = M1, Week 2 and 3 = M2, Week 4 = M3, Week 5 = M4, Week 6 = M5 and M6 in a smaller form.

### 15.2 What we cut or shrank relative to the PDF

- Pilot size (15 to 30 instead of 30 to 50) and duration (about one week instead of weeks across the winter break).
- Monetization, iOS, raids, achievements, Play Integrity, LiteRT model, corporate mode are not built.
- Play Console internal track is optional; APKs ship through GitHub Releases.
- Production-grade extras shrink if time runs out in this order: k6 load test, Trivy gate tuning, query-plan review, second restore drill. Not cut: backups with one tested restore, rollback script, monitoring basics.

### 15.3 Open decisions

| Decision | Owner | By |
|---|---|---|
| Which two buildings and faculties for seed data and the pilot | Both | Week 1 |
| Confirm the Azure for Students credit amount and eligibility | Ionut | Week 1 |
| Domain: student-pack domain or a cheap one | Ionut | Week 1 |
| Exact university e-mail domain(s) for the allow-list | Ionut | Week 2 |
| Background sync trigger: WorkManager from the native module or a JS background-fetch library | Cristea | Week 3 |
| Point values and diminishing-returns curve | Both | Week 3 |
| CI precision threshold for the trace-replay gate | Cristea | Week 2 |
| Accessible contribution mode rules | Both | Week 4 |
| Bring a third person for the pilot logistics (captains, recruiting)? | Both | Week 4 |

### 15.4 Glossary

| Term | Meaning |
|---|---|
| Segment | One detected ascent window with its features and classification. |
| Claim | The current owner of a building in a season. |
| Flip | A change of building owner. |
| Check-in | A 90-minute context that says which building the user is in. |
| Outbox | Local queue of segments waiting to upload. |
| Plausibility rules | Server checks on speed, cadence, steps per metre, pressure-steps match and rate. |
| Season | A two-week competition round (one week for the launch). |
| Raid | Stretch feature: one-hour team event with double points. |
| RPO / RTO | Maximum data loss / maximum time to recover. |
| PITR | Point-in-time recovery from WAL archives. |
| SOPS + age | Tools for encrypted secrets stored in git. |

### 15.5 Sources (from the PDF, FloorWars-relevant)

Competitors and context: StepJockey (gov.uk case study); Sahha guide to floors climbed; UBC Pick Your Peak; UCL Bentham Conquers Ben Nevis; Vantage Fit stair challenge guide.
Stack and prices: postgresql.org (18.x current; 19 in beta as of September 2026); PostGIS 3.6 release notes; GitHub Student Developer Pack offers (September 2026). The PDF also cited Oracle Cloud Always Free limits and Hetzner prices; we no longer use them.
Azure credit terms and instance prices were not in the PDF: check Azure's pages and calculator before relying on them. Re-check every price, quota and version.
