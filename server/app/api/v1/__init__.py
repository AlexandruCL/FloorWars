"""The ``/v1`` API (contract ``contracts/openapi.yaml``, server URL ``.../v1``).

Each feature is one module in this package with its own ``router = APIRouter(...)``, included
below. To add one (for example ``teams.py`` or ``checkins.py``): create the module, then add it to
``_FEATURE_ROUTERS``. Paths inside a module are relative to ``/v1`` (``/auth/otp``, ``/teams``).
"""

from fastapi import APIRouter

from app.api.v1 import auth, checkins, teams

_FEATURE_ROUTERS = (auth.router, teams.router, checkins.router)

router = APIRouter(prefix="/v1")
for _feature in _FEATURE_ROUTERS:
    router.include_router(_feature)
