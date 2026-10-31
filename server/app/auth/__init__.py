"""Authentication (plan 7.9): e-mail one-time codes, EdDSA access tokens, rotating refresh tokens.

- ``tokens``: access-token JWTs (our own code; ``cryptography`` only for Ed25519).
- ``otp``: code generation and hashing.
- ``ratelimit``: Valkey token buckets.
- ``repository``: all SQL of the feature (thin layer over the sync session).
- ``service``: the request-OTP, verify and refresh flows used by ``app.api.v1.auth``.
"""
