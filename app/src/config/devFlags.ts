// Test-build flag: makes sign-in skippable in release builds so testers can reach the sensor logger.
// Remove it (or set it to false) when the real auth (OTP sign-in) replaces the T7 stub.
export const DEV_SKIP_SIGN_IN = true;

// Forces has_barometer to false to exercise the landing-scan fallback on a phone that has one.
// Read only through hasBarometer(), which ignores it outside __DEV__ builds.
export const DEV_FORCE_NO_BAROMETER = false;
