"""Make ``server/`` importable (for ``app.qr_token``) in tools tests, whatever the import order."""

import sys
from pathlib import Path

_SERVER_DIR = str(Path(__file__).resolve().parents[1] / "server")
if _SERVER_DIR not in sys.path:
    sys.path.append(_SERVER_DIR)
