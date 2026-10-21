# FloorWars app

React Native 0.88.0 (bare, TypeScript), Android only. No Expo Go: run it as a development build.

The React Native version is pinned and stays at 0.88.0 for the whole project. All other dependencies are pinned to exact versions too (`.npmrc` sets `save-exact=true`).

## Prerequisites

- Node.js 22.11 or newer
- JDK 17
- Android SDK with platform 37, build-tools 37.0.0 and NDK 27.1.12297006 (versions come from `android/build.gradle`)
- `ANDROID_HOME` set to the SDK folder, with `platform-tools` on `PATH` so `adb` works
- An Android phone with USB debugging on, or a running emulator

Environment setup guide: https://reactnative.dev/docs/set-up-your-environment (pick Android as the target OS).

## Setup

From the repository root:

```sh
cd app
npm install
```

`npm install` also runs `prepare`, which points git at `app/.husky` for hooks. The pre-commit hook runs ESLint and Prettier on staged files through lint-staged.

## Checks

```sh
npm run lint
npm test
npx tsc --noEmit
```

Kotlin checks, from `android/`:

```sh
./gradlew ktlintCheck          # ktlintFormat fixes what it can
./gradlew testDebugUnitTest    # JUnit tests in app/src/test
```

## Run on a device or emulator

```sh
adb devices          # the phone or emulator must be listed
npm start            # Metro bundler, keep it running
npm run android      # in a second terminal: builds the debug APK and installs it
```

To build the debug APK without installing it:

```sh
cd android
./gradlew assembleDebug
```

The APK lands in `android/app/build/outputs/apk/debug/app-debug.apk`. Install it with `adb install -r android/app/build/outputs/apk/debug/app-debug.apk`.

## Release test build

A standalone APK with the JS bundle inside, for testers without Metro:

```sh
cd android
./gradlew assembleRelease
```

The APK lands in `android/app/build/outputs/apk/release/app-release.apk`. Install it with `adb install -r android/app/build/outputs/apk/release/app-release.apk`. It is signed with the debug keystore, so it is for testing only, not for the Play Store.

`DEV_SKIP_SIGN_IN` in `src/config/devFlags.ts` shows "Skip sign-in (dev)" in release builds so testers can reach the sensor logger. Set it to `false` or remove it when the real auth replaces the stub.

## API client (generated)

`src/api/schema.ts` is generated from `/contracts/openapi.yaml` by openapi-typescript. Do not edit it by hand, and don't reformat it (it is excluded from ESLint and Prettier). After a contract change:

```sh
npm run generate:api
```

Commit the regenerated file together with the contract change.

`package.json` has an `overrides` entry for openapi-typescript. openapi-typescript 7.13.0 (every 7.x release so far) declares a peer dependency on `typescript ^5.x`, and this app pins TypeScript 6.0.3, so `npm install` fails with ERESOLVE without it. The override points openapi-typescript at the app's own TypeScript instead of installing a second one; the generated output was checked under TypeScript 6 (`tsc --strict` and the contract test). Remove the override once an openapi-typescript release lists TypeScript 6 in its peer range, and upgrade to that release. Do not use `--force` or `--legacy-peer-deps` instead. `src/api/client.ts` is a small typed `fetch` wrapper over those types; it sends the stored access token as a bearer header. The base URL is the contract's placeholder (`API_BASE_URL` in `client.ts`) until the server is deployed.

The contract test is `__tests__/apiContract.typecheck.test.js`. It runs the TypeScript compiler over typed request and response samples in `__tests__/contract/samples.ts`, so `npm test` fails if the generated types and the samples drift apart. There is no CI yet, so it only runs locally.

## Hand-over for Ionut

Run the shell on your machine (prerequisites above; an emulator or a phone must show up in `adb devices`):

```sh
git clone https://github.com/AlexandruCL/FloorWars.git
cd FloorWars
git checkout feat/t7-api-client-auth-stub   # until T7 is merged into main
cd app
npm install
npm test             # should end with all tests passing
npm start            # Metro; keep this terminal open
npm run android      # second terminal: builds the debug APK and installs it
```

The app opens on Sign in. Tap "Sign in (stub)" and it should switch to Home. Tell Cristea whether it started and switched.

Calling the API from a screen:

```ts
import { api, ApiError } from '../api/client';

const floors = await api('get', '/buildings/{id}/floors', { path: { id: 1 } });
const result = await api('post', '/segments', {
  header: { 'Idempotency-Key': batchId },
  body: { segments },
});
```

Paths, parameters, bodies and responses are all typed from the contract, so a wrong field is a compile error. Non-2xx responses throw `ApiError` with `status` and the RFC 9457 `problem` body.

What the auth stub does: `signInWithStub` in `src/auth/authStub.ts` stores a dummy access token in the Android Keystore through react-native-keychain and switches the navigator from Auth to Main. It never calls the server, and the dummy token is sent as the bearer header. The real OTP sign-in (`/auth/otp`, `/auth/verify`, `/auth/refresh`) replaces it. When that lands, also remove `DEV_SKIP_SIGN_IN` (`src/config/devFlags.ts`) and the "Skip sign-in (dev)" button.

## Layout

```
App.tsx                         root component
src/navigation/RootNavigator.tsx  root stack switching between the Auth and Main stacks
src/navigation/types.ts         route param lists
src/screens/                    placeholder screens and the sensor logger
src/api/                        generated contract types (schema.ts) and the typed client
src/auth/authStub.ts            auth stub (dummy token in react-native-keychain)
__tests__/                      Jest tests
android/                        native Android project
```
