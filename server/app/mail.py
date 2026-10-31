"""Sign-in e-mail: a ``MailSender`` interface and its three backends.

``FLOORWARS_MAIL_BACKEND`` picks one (decision 2026-10-31):

- ``acs``: Azure Communication Services Email through its REST API, with our own HMAC-SHA256
  request signing (no Azure SDK). Production.
- ``log``: logs ``otp mail sent to <address>`` and drops the mail. Local development.
- ``fake``: keeps the mails in memory (``FakeMailSender.outbox``) for tests.

The code is in the mail body only: never log the body, the code or the request content.
"""

import base64
import hashlib
import hmac
import json
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from app.config import Settings

logger = logging.getLogger("floorwars.mail")

ACS_API_VERSION = "2023-03-31"
ACS_SEND_PATH = f"/emails:send?api-version={ACS_API_VERSION}"
# Explicit outbound timeouts (plan 7.10: connect 10 s, read 20 s).
ACS_TIMEOUT = httpx.Timeout(connect=10.0, read=20.0, write=20.0, pool=10.0)

OTP_SUBJECT = "Your FloorWars sign-in code"


class MailError(Exception):
    """The mail could not be handed to the provider. The message never contains the body."""


class MailSender(Protocol):
    """Sends the sign-in code. Implementations must not log ``code``."""

    def send_otp(self, to: str, code: str, ttl_s: int) -> None: ...


def otp_text(code: str, ttl_s: int) -> str:
    minutes = max(1, ttl_s // 60)
    return (
        f"Your FloorWars sign-in code is {code}.\n\n"
        f"It expires in {minutes} minutes. If you did not ask for it, ignore this e-mail."
    )


@dataclass(frozen=True)
class SentOtp:
    to: str
    code: str


class FakeMailSender:
    """Test backend: records every mail in ``outbox`` (thread-safe)."""

    def __init__(self) -> None:
        self.outbox: list[SentOtp] = []
        self._lock = threading.Lock()

    def send_otp(self, to: str, code: str, ttl_s: int) -> None:
        with self._lock:
            self.outbox.append(SentOtp(to=to, code=code))


class LogMailSender:
    """Dev backend: logs the recipient only."""

    def send_otp(self, to: str, code: str, ttl_s: int) -> None:
        logger.info("otp mail sent to %s", to)


# Azure Communication Services.
#
# Request signing follows "Sign an HTTP request with HMAC" for Azure Communication Services:
# https://learn.microsoft.com/en-us/azure/communication-services/tutorials/hmac-header-tutorial
# (checked 2026-10-31). Request body: "Email - Send", api-version 2023-03-31:
# https://learn.microsoft.com/en-us/rest/api/communication/email/email/send


def rfc1123(moment: datetime) -> str:
    """``x-ms-date`` value, for example ``Sat, 31 Oct 2026 12:00:00 GMT``."""
    return format_datetime(moment.astimezone(UTC), usegmt=True)


def acs_content_hash(body: bytes) -> str:
    """``x-ms-content-sha256``: base64 of the SHA-256 of the exact body bytes."""
    return base64.b64encode(hashlib.sha256(body).digest()).decode("ascii")


def acs_signed_headers(
    method: str, url: str, body: bytes, access_key_b64: str, moment: datetime
) -> dict[str, str]:
    """Headers that authenticate one ACS request with the resource access key.

    String to sign: ``<METHOD>\\n<path and query>\\n<x-ms-date>;<host>;<content hash>``, signed
    with HMAC-SHA256 using the base64-decoded access key, sent as
    ``HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature=<base64>``.
    """
    parts = urlsplit(url)
    path_and_query = parts.path + (f"?{parts.query}" if parts.query else "")
    host = parts.netloc
    date = rfc1123(moment)
    content_hash = acs_content_hash(body)
    string_to_sign = f"{method.upper()}\n{path_and_query}\n{date};{host};{content_hash}"
    key = base64.b64decode(access_key_b64)
    signature = base64.b64encode(
        hmac.digest(key, string_to_sign.encode("utf-8"), hashlib.sha256)
    ).decode("ascii")
    return {
        "x-ms-date": date,
        "x-ms-content-sha256": content_hash,
        "Authorization": (
            f"HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256&Signature={signature}"
        ),
    }


class AcsMailSender:
    """Production backend: ``POST {endpoint}/emails:send`` (202 Accepted on success)."""

    def __init__(
        self,
        endpoint: str,
        access_key_b64: str,
        sender: str,
        client: httpx.Client | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._url = endpoint.rstrip("/") + ACS_SEND_PATH
        self._key = access_key_b64
        self._sender = sender
        self._client = client or httpx.Client(timeout=ACS_TIMEOUT)
        self._clock = clock

    def build_body(self, to: str, code: str, ttl_s: int) -> bytes:
        message = {
            "senderAddress": self._sender,
            "recipients": {"to": [{"address": to}]},
            "content": {"subject": OTP_SUBJECT, "plainText": otp_text(code, ttl_s)},
            "userEngagementTrackingDisabled": True,
        }
        return json.dumps(message, separators=(",", ":")).encode("utf-8")

    def send_otp(self, to: str, code: str, ttl_s: int) -> None:
        body = self.build_body(to, code, ttl_s)
        operation_id = str(uuid.uuid4())
        headers = acs_signed_headers("POST", self._url, body, self._key, self._clock())
        headers["Content-Type"] = "application/json"
        headers["Operation-Id"] = operation_id
        try:
            response = self._client.post(self._url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.error(
                "acs send failed", extra={"error": type(exc).__name__, "operation": operation_id}
            )
            raise MailError("ACS request failed") from None
        if response.status_code != 202:
            logger.error(
                "acs send rejected",
                extra={
                    "status": response.status_code,
                    "acs_error": response.headers.get("x-ms-error-code"),
                    "operation": operation_id,
                },
            )
            raise MailError(f"ACS answered {response.status_code}")
        logger.info("otp mail sent", extra={"operation": operation_id})


def build_mail_sender(settings: Settings) -> MailSender:
    """The backend named by ``settings.mail_backend`` (settings already validated)."""
    if settings.mail_backend == "fake":
        return FakeMailSender()
    if settings.mail_backend == "log":
        return LogMailSender()
    if settings.acs_endpoint is None or settings.acs_access_key is None or not settings.mail_from:
        raise RuntimeError("mail_backend=acs needs mail_from, acs_endpoint and acs_access_key")
    return AcsMailSender(
        settings.acs_endpoint, settings.acs_access_key.get_secret_value(), settings.mail_from
    )
