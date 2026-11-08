## W3-4 and W3-5: sync worker, WorkManager job and status screen

Stacked on the outbox PR: until that merges, the diff also shows its commits.

- **W3-4:** `app/src/sync/` worker. Batches of up to 100 through the generated client with an `Idempotency-Key` derived from the sorted ids (a retry reuses it, a new batch gets a new one). `device_id` comes from `getDeviceId()`. Per-segment handling of accepted, rejected (any reason string is stored, never switched on) and repeats without `points`. Backoff with full jitter, `Retry-After` on 429 and 503, 401 through the existing refresh, a 422 or 403 `device-unknown` leaves the rows pending and reports a stuck state. Single flight. 10 s header and 20 s body timeouts in `client.ts`.
- **Background job:** WorkManager 2.12.0 (Apache 2.0), every 15 minutes with a network constraint, wakes the JS worker through Headless JS. It never uploads by itself.
- **W3-5:** Home becomes the status screen: detection, active check-in with minutes left, last segment, pending count, last upload, a Sync now button, the battery-optimisation hint (Android only, only when not exempt), and the Check in and Sensor logger buttons. Unknown values read "Unknown".

### Verify
- `cd app && npm run lint && npm run typecheck && npm test`: clean, 13 suites, 116 tests
- `npm run generate:api`: `schema.ts` unchanged
- `cd app/android && ./gradlew test ktlintCheck`: BUILD SUCCESSFUL

### Emulator click-through (API 36, debug build, Prism behind a small proxy for `/checkins` and `/segments`)
- Sign-in with an e-mail code and a team choice worked end to end; Home shows Status, Detection, Check-in, Last segment, Waiting to upload, Last upload.
- After a check-in: Detection "Running", Check-in "Building, 90 min left".
- A pending row in the outbox was uploaded on its own. The request carried exactly the ten segment fields, an `Idempotency-Key` and the app's `device_id`. A resend of the same row came back accepted without points and was marked synced.
- Airplane mode: "No connection to the server", row stays pending; after the network returned the row uploaded without a button press.
- Force-stop and reopen: the check-in, detection and pending rows were all still there.
- "Open battery settings" opened the system battery list.
- Not clicked: a 422 or 403 stuck state, the exempt-device case (hint hidden), a real climb.

### Not verified
The WorkManager job starts a plain service from the background, which Android may refuse on some versions. It was not run on a phone. Draining against plain Prism does not complete because Prism returns random ids; the proxy above echoed the sent ids.

Tested against the Prism mock and an emulator only, not the real server.
