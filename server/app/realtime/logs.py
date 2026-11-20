"""Keep the socket's ``access_token`` query value out of the logs.

Uvicorn logs the path with its query string for a WebSocket upgrade (``uvicorn.error``) and for
every HTTP request (``uvicorn.access``). ``configure_logging`` installs this filter on the stdout
handler, so every record is checked. Caddy deletes the parameter from its own log (Caddyfile).
"""

import logging
import re
from urllib.parse import unquote_plus

# Any query parameter; its key is compared after percent-decoding, because Starlette decodes the
# key too (``access%5Ftoken`` or ``%61ccess_token`` authenticate like ``access_token``).
_PARAM = re.compile(r"([?&;])([^=&\s\"']+)=([^&\s\"']*)")


def _redact(match: re.Match[str]) -> str:
    if unquote_plus(match.group(2)).lower() != "access_token":
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}=[redacted]"


class RedactAccessToken(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _PARAM.sub(_redact, message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True
