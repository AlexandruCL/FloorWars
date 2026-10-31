"""Mail backends and the ACS request signature. No database or network needed."""

import json
import logging
from datetime import UTC, datetime

import httpx
import pytest

from app.config import Settings
from app.mail import (
    AcsMailSender,
    FakeMailSender,
    LogMailSender,
    MailError,
    acs_signed_headers,
    build_mail_sender,
)

# Test vector computed with the Python code of Microsoft's "Sign an HTTP request with HMAC"
# tutorial (an independent implementation). The key is a dummy, not a real access key.
KEY = "Zmxvb3J3YXJzLXRlc3Qta2V5LW5vdC1hLXNlY3JldCE="
URL = "https://example.communication.azure.com/emails:send?api-version=2023-03-31"
BODY = b'{"hello":"world"}'
MOMENT = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)
EXPECTED = {
    "x-ms-date": "Sat, 31 Oct 2026 12:00:00 GMT",
    "x-ms-content-sha256": "k6I5cakU5erL8KjSUVTNownDwccvu5kU1Hxg88toFYg=",
    "Authorization": (
        "HMAC-SHA256 SignedHeaders=x-ms-date;host;x-ms-content-sha256"
        "&Signature=fC+jZoLbMo+qzAGh+Guf0IkI467bW3Ef/O9znX6ERIo="
    ),
}


def test_acs_signature_vector() -> None:
    assert acs_signed_headers("POST", URL, BODY, KEY, MOMENT) == EXPECTED


def _acs_sender(handler: httpx.MockTransport) -> AcsMailSender:
    return AcsMailSender(
        "https://example.communication.azure.com",
        KEY,
        "DoNotReply@example.azurecomm.net",
        client=httpx.Client(transport=handler),
        clock=lambda: MOMENT,
    )


def test_acs_sender_posts_signed_request() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json={"id": "x", "status": "Running"})

    _acs_sender(httpx.MockTransport(handle)).send_otp("a@student.upt.ro", "123456", 600)

    (request,) = seen
    assert str(request.url) == URL
    body = request.content
    assert (
        request.headers["authorization"]
        == (acs_signed_headers("POST", URL, body, KEY, MOMENT)["Authorization"])
    )
    message = json.loads(body)
    assert message["recipients"] == {"to": [{"address": "a@student.upt.ro"}]}
    assert message["senderAddress"] == "DoNotReply@example.azurecomm.net"
    assert "123456" in message["content"]["plainText"]


def test_acs_failure_raises_without_leaking_the_code(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    sender = _acs_sender(httpx.MockTransport(lambda _: httpx.Response(401)))
    with pytest.raises(MailError):
        sender.send_otp("a@student.upt.ro", "654321", 600)
    assert "654321" not in caplog.text


def test_log_backend_logs_address_not_code(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    LogMailSender().send_otp("b@student.upt.ro", "987654", 600)
    assert "otp mail sent to b@student.upt.ro" in caplog.text
    assert "987654" not in caplog.text


def test_build_mail_sender_picks_backend() -> None:
    assert isinstance(build_mail_sender(Settings(mail_backend="fake")), FakeMailSender)
    assert isinstance(build_mail_sender(Settings(mail_backend="log")), LogMailSender)
    acs = Settings(
        mail_backend="acs",
        mail_from="DoNotReply@example.azurecomm.net",
        acs_endpoint="https://example.communication.azure.com",
        acs_access_key=KEY,  # type: ignore[arg-type]
    )
    assert isinstance(build_mail_sender(acs), AcsMailSender)
