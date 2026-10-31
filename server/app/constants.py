"""Constants shared by settings, models and services (no imports, so anything may import it)."""

HOUR_S = 3600
DAY_S = 24 * HOUR_S

# Highest value of otp_challenge.attempts (plan 7.9: five attempts per code). The model's CHECK
# uses it; migration 0002_auth hard-codes the same 5 (migrations are frozen), so changing this
# needs a new migration for the CHECK. Settings bound ``otp_max_attempts`` by it.
OTP_MAX_ATTEMPTS = 5
