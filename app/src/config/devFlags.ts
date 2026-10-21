// Test-build flag: makes sign-in skippable in release builds so testers can reach the sensor logger.
// Remove it (or set it to false) when the real auth (OTP sign-in) replaces the T7 stub.
export const DEV_SKIP_SIGN_IN = true;
