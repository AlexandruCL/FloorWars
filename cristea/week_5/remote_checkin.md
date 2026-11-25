# Remote check-in

Week 5, Cristea. Decided 2026-11-25.

## Why

Players should be able to fight for a building from anywhere: pick a team and a building, then climb any stairs, home included. Today only the check-in ties a player to the faculty: it needs the entrance QR code or a location fix within 30 m of the building. Climb verification never looks at location. It needs an active check-in of the user that contains the climb's `started_at` (`server/app/segments/rules.py`, `_check_state`). So a check-in method without location is enough. Nothing else in the pipeline changes.

## Decisions

- A new check-in method `pick`: the player chooses a building from a list.
- Every check-in lasts 24 h (today 90 minutes).
- Switching to a different building is locked for 24 h after the last switch, for every method, QR included. Checking in again to the same building is always allowed and renews the 24 h.
- QR stays: scanning the entrance code at the faculty checks the player in to that building in one step.
- The geofence button leaves the app. The server endpoint stays for now.

## Server

- `server/app/api/v1/checkins.py`: add `PickCheckinRequest {method: "pick", building_id: int >= 1}` to the discriminated union. Add `"pick"` to the response `Checkin.method` literal and return `created.method` as it is, in place of the qr/geofence ternary. The docstring says 24 hours.
- `server/app/checkins/service.py`: `checkin_by_pick(db, settings, user_id, building_id)` checks `repository.building_exists` (403 `building-unknown`, as the QR flow does), then calls `_record(..., "pick")`.
- Cooldown, in `_record` after `lock_user` and `db_clock`: the switch time is the earliest `valid_from` of the user's check-ins in their latest building after their last check-in in any other building. If the new building differs and `now - switch time < building_switch_cooldown_s`, roll back and answer 403 `urn:floorwars:problem:building-locked` with the unlock time in the detail. The query goes in `server/app/checkins/repository.py`.
- `server/app/config.py`: `checkin_ttl_s` default 86400 (already the `le=DAY_S` limit); new `building_switch_cooldown_s`, default 86400.
- Migration: `ck_checkin_method` becomes `method IN ('qr', 'geofence', 'pick')`. Same change to `CHECKIN_METHODS` and the constraint in `server/app/db/models.py`.
- Remove the `impossible_sequence` flag. With 24 h check-ins, climbs in two buildings say nothing about where the player was. Delete `MAX_WALK_SPEED_MPS` and the literal in `rules.py`, `impossible_sequences` in `segments/repository.py`, its call in `segments/service.py`, its tests in `tests/segments/test_anticheat.py` and its line in `server/README.md`. Old `fraud_flag` rows with that rule stay valid: do not narrow any constraint on the rule column.
- `contracts/openapi.yaml`: the `pick` variant of `CheckinRequest`, `pick` in `Checkin.method`, the 403 `building-locked` case. Bump the draft version. Ionut reviews.

## App

- Regenerate the client with the `api-client-regen` skill.
- `app/src/checkin/state.ts`: `Method = 'qr' | 'pick'`; a `locked` error kind that shows the unlock time.
- `app/src/screens/CheckinScreen.tsx`: a building list from `GET /v1/buildings` replaces the geofence button. Tapping a building sends `{method: 'pick', building_id}`. The QR scanner stays as it is. Drop the location permission and its onboarding copy if nothing else uses them.
- Update `app/__tests__/checkin.test.tsx` and `app/__tests__/contract/samples.ts`.

## Tests

Server:
- `pick` answers 201 with method `pick` and a 24 h window.
- An unknown building answers 403 `building-unknown`.
- Switching building inside 24 h answers 403 `building-locked`, for `pick` and for `qr`.
- Checking in again to the same building is allowed and renews the window.
- Switching after 24 h is allowed.
- A climb uploaded after a `pick` check-in is verified, end to end.

App:
- Tapping a building submits `pick`.
- A 403 `building-locked` shows the locked message with the unlock time.

## Done when

- `pytest` in `server/`, `npm test` in `app/` and the contract tests pass.
- On the emulator: pick a building away from the faculty, replay a trace, the climb is verified and the standings move. Switching to another building within 24 h shows the locked message.
- The section 1, 2, 3, 5, 6 and glossary lines of `IMPLEMENTATION_PLAN.md` that say 90 minutes or "QR or geofence" are updated in the same PR.

Branch `feat/remote-checkin`. Open the PR only when Cristea says.
