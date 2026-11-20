"""Keep the socket's ``access_token`` query value out of the logs.

Uvicorn logs the path with its query string for a WebSocket upgrade (``uvicorn.error``) and for
every HTTP request (``uvicorn.access``). ``configure_logging`` installs this filter on the stdout
handler, so every record is checked. Caddy deletes the parameter from its own log (Caddyfile).
"""

import logging
import re

_TOKEN = re.compile(r"(access_token=)[^&\s\"']*")


class RedactAccessToken(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if "access_token=" in message:
            record.msg = _TOKEN.sub(r"\1[redacted]", message)
            record.args = None
        return True
