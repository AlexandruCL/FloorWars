# FloorWars

**Take the stairs, take the building.** A campus territory game. Every sensor-verified stair climb adds points to your faculty's claim on a real building. Phones with a barometer and a step detector do the verification, so no hardware goes into the buildings.

Team: **Cristea** (Member A) and **Ionut** (Member B). Client: React Native (bare, TypeScript), Android first. Backend: FastAPI, PostgreSQL with PostGIS, Valkey, Celery (planned, see the plan).

The full project reference and six-week plan is [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md). It is the single source of truth. This README gives the overview and the decisions taken so far.

## Status

| Area | State |
|---|---|
| Week 1, code | Done: app shell, Kotlin sensor module, foreground service, sensor logger, API client and auth stub, contract, release test build |
| Week 1, synthetic data | Done: 24 labelled synthetic traces, generator, checker, trace spec |
| Week 1, real phones | Open: phone checks, real recordings, device details (see `cristea/phone_tests.md`) |
| Building territory | Plan, scoring rule, floor-equivalent helper and contract revision merged |
| Backend | Not started (week 2 onwards) |

## How the game works

- **Territory is per building.** A building is the claimed object. The team with the most points in a building over the rolling 7-day window owns it.
- **Points come from verified stair steps.** A segment scores only if its step count matches its pressure change: stairs need about 4 to 8 steps per metre of ascent. Elevator rides, flat walking and shaking score nothing.
- **Floors are a display estimate.** 20 verified steps is shown as one "floor (estimate)". It is never a real storey number.
- **No building data is required.** Ascent is measured in metres from the barometer. The app does not know floor counts, heights or room positions.
- **Anti-cheat:** on-device classifier, server-side plausibility checks, per-user rate limits, signed expiring QR codes at the entrance.

## Decisions taken

Dates are when the decision was made. The rule that is in force is in the plan and in the docs linked below.

| Date | Decision | Where |
|---|---|---|
| 2026-10-21 | Bare React Native, TypeScript, Android first. Kotlin native module `FloorSensors` for sensing. | Plan section 4 |
| 2026-10-21 | Foreground service of type `health` for logging. Pressure and step detector registered at game rate. | `app/android` |
| 2026-10-21 | API contract approved by both members. Every later change is a reviewed PR. | `contracts/openapi.yaml` |
| 2026-10-21 | Week 1 can be completed on synthetic data. Synthetic traces are labelled and never counted as real. | `docs/trace_format.md`, `fixtures/synthetic/` |
| 2026-10-21 | Friend test builds use a release APK with a dev-only skip sign-in flag. The flag is removed when the real auth replaces the stub. | `app/src/config/devFlags.ts` |
| 2026-10-22 | Requirement: runs on any Android phone with a barometer. Capabilities are checked at run time. No dependency on phone model names. | `cristea/phone_tests.md` |
| 2026-10-22 | No building floor data. Ascent is measured in metres. Floors removed as a game unit. | Plan sections 2, 3, 5, 6 |
| 2026-10-22 | Territory per building. Points per verified stair step, with a pressure-steps match (the scoring rule). | Plan section 3.3 |
| 2026-10-22 | Floor-equivalent for display only: 20 steps = 1 floor, labelled "floors (estimate)". | Plan section 2, `app/src/scoring/floorEquivalent.ts` |

Starting values are ours and tunable from real data: 1 point per verified step, halving after 300 steps in an hour, at most 600 verified steps per 10 minutes per user, 20 steps per floor-equivalent.

## Repository layout

| Path | What is there |
|---|---|
| `IMPLEMENTATION_PLAN.md` | Project reference and six-week plan (source of truth) |
| `app/` | React Native app and Kotlin native module (`FloorSensors`). See `app/README.md` for setup and the release test build |
| `contracts/openapi.yaml` | API contract (OpenAPI 3.1) |
| `cristea/` | Cristea's week 1 tasks and status |
| `docs/` | Trace format and expected values (`trace_format.md`), test device log (`devices.md`) |
| `fixtures/synthetic/` | Synthetic labelled traces for week 1. Not real data |
| `tools/synthetic_traces/` | Seeded generator for the synthetic traces |
| `tools/validate_traces/` | Checker for trace files against `docs/trace_format.md` (checks 1 to 9) |

## Getting started

1. Clone the repo.
2. For the app: `cd app`, `npm install`, `npm test`, then `npm start` and `npm run android`. The full steps, including the Android SDK setup, are in `app/README.md`.
3. For the contract: `contracts/openapi.yaml`. Regenerate the client with `npm run generate:api` in `app/`.
4. For traces: `python tools/validate_traces/validate.py <dir_or_file>`.

## Working rules

- One branch per task, one PR into `main`. The other member reviews.
- No co-author trailers on commits.
- Don't commit APKs, keystores, `local.properties`, or real recordings that haven't been checked for personal data.
- Changes to the approved contract go through review by the other member.
- Plan changes go on the plan branch first, then into `main`.

## Open work

- Real-phone tests and real recordings: see `cristea/phone_tests.md`.
- Backend and database (weeks 2 to 5): see the plan.
- Auth: replace the stub and remove the dev skip flag (T7 follow-up).
- CI: none yet. The contract test runs under `npm test` locally.
- Dependency audit: the app reports 54 npm vulnerabilities (5 moderate, 49 high). Not yet triaged.
