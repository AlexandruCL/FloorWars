# Prism mock of the API

A mock server generated from `contracts/openapi.yaml`, so the app can be built before the backend exists (plan section 9.2). Prism runs through `npx`; nothing is installed globally or added to `app/package.json`.

Pinned version: `@stoplight/prism-cli@5.14.2`. Needs Node 18 or later (tested with Node 24).

## Start it

From the repository root:

```sh
npx --yes @stoplight/prism-cli@5.14.2 mock contracts/openapi.yaml --port 4010
```

or `npm run mock:api` (the same command, defined in the root `package.json`).

Dynamic mode returns random data that fits the schemas instead of the same fixed body every time:

```sh
npx --yes @stoplight/prism-cli@5.14.2 mock contracts/openapi.yaml --port 4010 --dynamic
```

or `npm run mock:api:dynamic`. Stop it with Ctrl+C.

## What the mock does and does not do

- **No `/v1` prefix.** Prism ignores the base path of the contract's `servers` URL and serves every path at the root: `http://127.0.0.1:4010/segments`, not `/v1/segments`. A request to `/v1/...` gets 404 "Route not resolved".
- **Requests are validated.** A missing bearer token gives 401. A missing `Idempotency-Key`, a body that is not a valid batch, a value outside the schema bounds (for example `steps: 0`) or a bad UUID gives 422.
- **Unknown fields slip through.** Prism does not enforce `unevaluatedProperties: false` on `Segment`, so an extra field such as `floors_gained` is accepted by the mock. The real server must reject it.
- **Responses are canned.** The contract has no examples, so static mode fills in placeholders: `POST /segments` always answers one accepted item, one rejected item (`pressure_steps_mismatch`) and one flip, with ids that do not match the request and team codes `"string"`. Error bodies are placeholders too. Use `--dynamic` to see varied data.
- **No state and no rules.** The mock does not score, does not apply the 4 to 8 steps per metre rule, does not remember idempotency keys and never pushes WebSocket events.

## Point the app at it

The base URL is `API_BASE_URL` in `app/src/api/client.ts`. For local mock work, change it on your machine (do not commit it) to:

| Where the app runs | Base URL |
|---|---|
| Android emulator | `http://10.0.2.2:4010` (the emulator's alias for the host's 127.0.0.1) |
| Physical phone over USB | run `adb reverse tcp:4010 tcp:4010`, then `http://127.0.0.1:4010` |
| Physical phone over Wi-Fi | `http://<computer LAN IP>:4010`, start Prism with `--host 0.0.0.0` |

The mock is plain `http`. The debug build allows it (`usesCleartextTraffic` in `AndroidManifest.xml` is true for debug builds via the React Native Gradle plugin); the release test APK does not, so use a debug build against the mock. The mock accepts any bearer token, so the dev skip sign-in flag is enough.

## Post fake segments to it

```sh
python tools/fake_segments/fake_segments.py --count 5 --batch-size 5
python tools/fake_segments/fake_segments.py --count 5 --batch-size 5 --repeat-last
```

The script's default base URL is the mock (`http://127.0.0.1:4010`) and its default token is a dummy. See `tools/fake_segments/README.md`.

## If npx fails

`npm error code ECOMPROMISED` / `Lock compromised`, or later `Cannot find module ...`, means npm's `_npx` cache entry was left half-installed (seen with npm 11 on Windows). Run once with a fresh cache folder:

```sh
npx --yes --cache <some empty folder> @stoplight/prism-cli@5.14.2 mock contracts/openapi.yaml --port 4010
```
