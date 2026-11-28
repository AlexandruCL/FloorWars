# Caddy with the per-IP rate limiter (plan 7.4/7.11). The stock caddy image has none.
# Build context: infra/caddy. Local: compose.local.yml builds it; production pulls it from GHCR.
# Keep both tags on the same Caddy version.
ARG CADDY_VERSION=2.11.9

FROM caddy:${CADDY_VERSION}-builder AS builder
# mholt/caddy-ratelimit has no release since v0.1.0, so it is pinned by commit (2026-06-12).
RUN xcaddy build \
    --with github.com/mholt/caddy-ratelimit@5625512f24f6f59d6f64fb3aafe5eecff0b286db

FROM caddy:${CADDY_VERSION}
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
