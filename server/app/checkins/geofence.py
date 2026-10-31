"""Geofence check-in: match a one-shot location fix to a building (plan 3.2, 8).

The fix is used for this lookup only: it is never stored, logged or echoed back.
"""

from sqlalchemy.orm import Session

from app.api.problems import forbidden
from app.checkins import repository
from app.config import Settings

LOCATION_INACCURATE = "urn:floorwars:problem:location-inaccurate"
OUTSIDE_GEOFENCE = "urn:floorwars:problem:outside-geofence"


def locate_building(
    db: Session, settings: Settings, latitude: float, longitude: float, accuracy_m: float | None
) -> int:
    """Id of the nearest building within ``geofence_radius_m`` of the fix, or a 403 problem.

    A fix less accurate than ``geofence_max_accuracy_m`` is refused before any lookup. A fix
    without ``accuracy_m`` is accepted as is.
    """
    if accuracy_m is not None and accuracy_m > settings.geofence_max_accuracy_m:
        raise forbidden("The location fix is not accurate enough.", type_=LOCATION_INACCURATE)
    building_id = repository.nearest_building_id(
        db, latitude, longitude, settings.geofence_radius_m
    )
    if building_id is None:
        raise forbidden("No building is close enough to this position.", type_=OUTSIDE_GEOFENCE)
    return building_id
