# T1 handoff: Init React Native app

Status: **not done**. Code is committed and every JS check passes. The debug APK has not been built or installed yet. The emulator was too heavy for this laptop, so the build was stopped partway.

Branch: `feat/t1-rn-app-init`, commit `c53a60a`. Not pushed, no PR yet.

## Done

- `/app`: React Native 0.88.0, TypeScript, bare, Android only. iOS template files (`ios/`, `Gemfile`, `.bundle`) deleted.
- All dependencies pinned to exact versions in `package.json`. `.npmrc` has `save-exact=true` so new installs stay pinned.
- React Navigation: `src/navigation/RootNavigator.tsx` holds a root stack that shows either the `Auth` stack (`SignIn`) or the `Main` stack (`Home`), based on an `isSignedIn` prop. `App.tsx` passes `false` until the T7 auth stub exists. Placeholder screens are in `src/screens/PlaceholderScreens.tsx`.
- `MainActivity.kt`: added the `RNScreensFragmentFactory` override that react-native-screens requires on Android.
- ESLint (`@react-native/eslint-config`), Prettier, Jest + React Native Testing Library 14 (its `render` is async). `jest.setup.js` mocks safe-area-context.
- Husky + lint-staged. `prepare` runs `cd .. && husky app/.husky`, which sets the repo's `core.hooksPath` to `app/.husky`. Tested by the T1 commit itself.
- `__tests__/App.test.tsx`: two tests, one per stack.
- `app/README.md`: prerequisites, setup, checks, run and APK commands.

## Check output (2026-10-21)

```
$ npm install
exit 0          (npm audit reports some advisories; not reviewed)
$ npm run lint
exit 0
$ npm test
PASS __tests__/App.test.tsx
  √ App starts on the Auth stack
  √ signed-in users get the Main stack
Tests: 2 passed, 2 total
exit 0
$ npx tsc --noEmit
exit 0
```

## Machine setup done during T1 (not in git)

- Android SDK at `C:\Users\alexc\AppData\Local\Android\Sdk`, installed with cmdline-tools 16111833 (sha1 checked). It holds platform-tools, `platforms/android-37.0`, build-tools 37.0.0, NDK 27.1.12297006, the emulator, and the `system-images/android-36/google_apis/x86_64` image. SDK licenses accepted.
- AVD `floorwars_api36` (pixel_7, API 36). It booted once and was shut down.
- `app/android/local.properties` contains `sdk.dir=C\:/Users/alexc/AppData/Local/Android/Sdk` (gitignored). Use forward slashes: backslashes are escape characters in `.properties` files. With backslashes the build fails with "The filename, directory name, or volume label syntax is incorrect".
- `ANDROID_HOME` is not set system-wide and `adb` is not on `PATH`. Full path: `C:\Users\alexc\AppData\Local\Android\Sdk\platform-tools\adb.exe`.
- New sdkmanager package ids use `/` (for example `platforms/android-37.0`). Ids with `;` get split by the `.bat` wrapper when called from Git Bash. Use `--package_file=<file>`.

## Remaining to close T1

1. Build the APK (no emulator needed). The first build downloaded Gradle 9.4.1 and got through configuration and about 150 tasks before it was stopped on purpose.
   ```sh
   cd app/android
   ./gradlew assembleDebug
   ```
   Output: `app/android/app/build/outputs/apk/debug/app-debug.apk`.
2. Install it on one device. A physical phone is lighter than the emulator: turn on USB debugging, plug it in, accept the RSA prompt, then:
   ```sh
   adb devices
   adb install -r app/android/app/build/outputs/apk/debug/app-debug.apk
   ```
   Or run `npm start`, then `npm run android` from `app/`. Check that the app opens on the "Sign in" placeholder.
3. Push the branch and open a PR into `main` that includes the check output and the APK install result. Ionut reviews.
4. Report to the Planner session: result plus the command output above.

## Notes for review

- No CI workflow exists yet, so "CI green before merge" has nothing to check. CI was not in T1 scope.
- `core.autocrlf` is on. Files are committed with LF and Git warns about CRLF in the working copy. `gradlew` is LF in the index, so Linux CI is fine. Add `.gitattributes` if CRLF causes trouble later.
- `cristea/week_1_tasks.md` was untracked before T1 started and is not in the T1 commit.
