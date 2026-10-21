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

`DEV_SKIP_SIGN_IN` in `src/config/devFlags.ts` shows "Skip sign-in (dev)" in release builds so testers can reach the sensor logger. Set it to `false` or remove it before T7 (auth stub) lands.

## Layout

```
App.tsx                         root component
src/navigation/RootNavigator.tsx  root stack switching between the Auth and Main stacks
src/navigation/types.ts         route param lists
src/screens/                    placeholder screens
__tests__/                      Jest tests
android/                        native Android project
```
