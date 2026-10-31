"""Application settings (twelve-factor, plan section 7.5).

Values come from environment variables prefixed with ``FLOORWARS_``. In deployed
environments secrets are files in ``/run/secrets`` (decrypted by ``deploy.sh`` from SOPS);
a file named after the prefixed variable (for example ``/run/secrets/floorwars_database_url``;
pydantic-settings applies ``env_prefix`` to secret file names) is read when the directory
exists. Local runs without that directory fall back to plain environment variables.

Secrets (connection strings, keys) are ``SecretStr`` so they never show up in reprs or logs.
Every variable is documented in ``server/.env.example`` and ``server/README.md``.

Every setting except the database URL is optional when ``Settings`` is built: the migration
container (Alembic's ``env.py`` loads ``Settings``) gets only ``floorwars_database_url``. Values
that are given are format-checked here (hex keys, base64 ACS key, https endpoint).

The API checks what it needs at startup (``check_api_settings``, called by ``create_app``; on
failure the app refuses to start):

- ``FLOORWARS_ENV=prod`` needs ``mail_backend=acs`` (decision 2026-10-31);
- ``mail_backend=acs`` needs ``mail_from``, ``acs_endpoint`` and ``acs_access_key``;
- ``staging`` and ``prod`` need ``jwt_signing_key`` and refuse the ``fake`` mail backend. In
  ``dev`` a missing ``jwt_signing_key`` is replaced by a random key per process.

``qr_hmac_key`` is only defined here; the check-in feature enforces it where it uses it.
"""

import base64
import binascii
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.db.models import OTP_MAX_ATTEMPTS

SECRETS_DIR = Path("/run/secrets")

Environment = Literal["dev", "staging", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
# acs: Azure Communication Services (production); log: logs "otp mail sent to <address>"
# without the code (local dev); fake: in-memory outbox read by tests.
MailBackend = Literal["acs", "log", "fake"]

HOUR_S = 3600
DAY_S = 24 * HOUR_S


def _hex32(value: SecretStr | None, name: str) -> SecretStr | None:
    """Accept a 32-byte key written as 64 hex characters (one line, as ``deploy.sh`` needs)."""
    if value is None:
        return None
    raw = value.get_secret_value().strip()
    try:
        decoded = bytes.fromhex(raw)
    except ValueError:
        raise ValueError(f"{name} must be hex") from None
    if len(decoded) != 32:
        raise ValueError(f"{name} must be 32 bytes (64 hex characters)")
    return SecretStr(raw.lower())


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLOORWARS_",
        secrets_dir=SECRETS_DIR if SECRETS_DIR.is_dir() else None,
        case_sensitive=False,
        extra="ignore",
        # A failed startup check must not print the raw inputs (they include the secrets).
        hide_input_in_errors=True,
    )

    env: Environment = "dev"
    log_level: LogLevel = "INFO"
    database_url: SecretStr | None = None
    valkey_url: SecretStr | None = None

    # Sign-in (plan 7.9). Comma-separated list in the environment, compared lower-case.
    allowed_email_domains: Annotated[tuple[str, ...], NoDecode] = ("student.upt.ro",)

    # Sign-in e-mail.
    mail_backend: MailBackend = "log"
    mail_from: str | None = None  # ACS sender, e.g. DoNotReply@<id>.azurecomm.net
    acs_endpoint: str | None = None  # https://<resource>.communication.azure.com
    acs_access_key: SecretStr | None = None  # base64 access key of the ACS resource

    # Tokens (plan 7.9). The signing key is the hex of a 32-byte Ed25519 seed, not a PEM.
    jwt_signing_key: SecretStr | None = None
    jwt_audience: str = "floorwars-api"
    access_token_ttl_s: int = Field(default=900, ge=60, le=DAY_S)
    refresh_token_ttl_s: int = Field(default=30 * DAY_S, ge=HOUR_S, le=365 * DAY_S)

    # One-time codes (plan 7.9: 10 minutes, at most 5 attempts).
    otp_ttl_s: int = Field(default=600, ge=60, le=HOUR_S)
    otp_max_attempts: int = Field(default=OTP_MAX_ATTEMPTS, ge=1, le=OTP_MAX_ATTEMPTS)
    # Valkey token buckets for POST /v1/auth/otp (plan 3.4, 7.11).
    otp_rate_per_email_per_hour: int = Field(default=5, ge=1, le=1000)
    otp_rate_per_ip_per_hour: int = Field(default=60, ge=1, le=100_000)
    # Per client IP (IPv6 per /64) on /auth/verify and /auth/refresh, checked before any database
    # work. Generous: the campus NAT puts many students behind one address.
    verify_rate_per_ip_per_hour: int = Field(default=300, ge=1, le=100_000)
    refresh_rate_per_ip_per_hour: int = Field(default=1200, ge=1, le=100_000)

    # Entrance QR signatures (HMAC-SHA256, 32 bytes as hex). Used by the check-in feature.
    qr_hmac_key: SecretStr | None = None

    @field_validator("allowed_email_domains", mode="before")
    @classmethod
    def _split_domains(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.split(",")
        if isinstance(value, list | tuple):
            domains = tuple(str(d).strip().lower().lstrip("@") for d in value if str(d).strip())
            if not domains:
                raise ValueError("at least one allowed e-mail domain is needed")
            return domains
        return value

    @field_validator("jwt_signing_key")
    @classmethod
    def _check_jwt_key(cls, value: SecretStr | None) -> SecretStr | None:
        return _hex32(value, "jwt_signing_key")

    @field_validator("qr_hmac_key")
    @classmethod
    def _check_qr_key(cls, value: SecretStr | None) -> SecretStr | None:
        return _hex32(value, "qr_hmac_key")

    @field_validator("acs_access_key")
    @classmethod
    def _check_acs_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        try:
            base64.b64decode(value.get_secret_value().strip(), validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("acs_access_key must be base64") from None
        return SecretStr(value.get_secret_value().strip())

    @field_validator("acs_endpoint")
    @classmethod
    def _check_acs_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = urlsplit(value.strip())
        if parts.scheme != "https" or not parts.netloc or parts.path not in ("", "/"):
            raise ValueError("acs_endpoint must be https://<resource>.communication.azure.com")
        return f"https://{parts.netloc}"


class ConfigError(RuntimeError):
    """The settings are not enough to run the API. Names variables, never values."""


def check_api_settings(settings: Settings) -> None:
    """Refuse to start the API with an unusable configuration (see the module docstring)."""
    if settings.mail_backend == "acs":
        missing = [
            f"FLOORWARS_{name.upper()}"
            for name in ("mail_from", "acs_endpoint", "acs_access_key")
            if getattr(settings, name) is None
        ]
        if missing:
            raise ConfigError(f"FLOORWARS_MAIL_BACKEND=acs needs {', '.join(missing)}")
    if settings.env == "prod" and settings.mail_backend != "acs":
        raise ConfigError("FLOORWARS_ENV=prod needs FLOORWARS_MAIL_BACKEND=acs")
    if settings.env in ("staging", "prod"):
        if settings.mail_backend == "fake":
            raise ConfigError("the fake mail backend is for tests only")
        if settings.jwt_signing_key is None:
            raise ConfigError(f"FLOORWARS_ENV={settings.env} needs FLOORWARS_JWT_SIGNING_KEY")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return Settings()
