"""Application settings (twelve-factor, plan section 7.5).

Values come from environment variables prefixed with ``FLOORWARS_``. In deployed
environments secrets are files in ``/run/secrets`` (decrypted by ``deploy.sh`` from SOPS);
a file named after the field (for example ``/run/secrets/database_url``) is read when the
directory exists. Local runs without that directory fall back to plain environment variables.

Connection strings are ``SecretStr`` so they never show up in reprs or logs.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")

Environment = Literal["dev", "staging", "prod"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FLOORWARS_",
        secrets_dir=SECRETS_DIR if SECRETS_DIR.is_dir() else None,
        case_sensitive=False,
        extra="ignore",
    )

    env: Environment = "dev"
    log_level: LogLevel = "INFO"
    # Optional until the database and Valkey are wired in (Week 1 / Week 2).
    database_url: SecretStr | None = None
    valkey_url: SecretStr | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, read once."""
    return Settings()
