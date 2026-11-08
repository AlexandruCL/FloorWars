## Show the team picker again when a new season starts

Ionut found a real gap: when a season rolls over, existing users have no membership in the new one, and the app only remembered a "team chosen" flag, so it let them in and every upload came back `no_team`. This is independent of the other W3 PRs and branches from `main`.

- The app now stores the **season id** it joined (the old flag `1` is read as season 1, the only season that existed, so existing installs migrate on their own).
- On app start, with a session, it reads `GET /seasons/active`. If the running season is not the joined one, it shows the team picker. If the season cannot be read (offline, none running) the user stays in and it is checked again on the next start.
- Joining: only `urn:floorwars:problem:already-joined` counts as already joined. A `season-not-active` 409 (a join before the season starts) used to be swallowed as "already joined" and would have marked the user as joined with no membership. It now shows "The season is not running right now. Try again when it starts." and does not mark the team chosen.

### Verify
- `cd app && npm run lint && npm run typecheck && npm test`: clean, 10 suites, 82 tests (5 new)
- Breaking either fix makes exactly the related tests fail (checked once, then restored).

### Not verified or not covered
Not run on an emulator or a phone, and not against the real server. The check runs at app start only: a user who keeps the app open across the 00:00 UTC rollover sees the picker after the next start (or sign-out and sign-in). Season 2 starts on 2026-11-09 at 00:00 UTC.
