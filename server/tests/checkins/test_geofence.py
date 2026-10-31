"""POST /v1/checkins with method=geofence, and the GiST index used by its query."""

from typing import Any

from sqlalchemy import text

from tests.checkins.conftest import (
    CENTRE_LAT,
    CENTRE_LON,
    Ctx,
    dlon,
    east_of_edge,
    geo_body,
    insert_building,
)


def _post(ctx: Ctx, body: dict[str, Any]) -> Any:
    return ctx.client.post("/v1/checkins", json=body, headers=ctx.headers)


def _type(response: Any) -> str:
    assert response.headers["content-type"].startswith("application/problem+json")
    return str(response.json()["type"])


def test_inside_footprint(ctx: Ctx) -> None:
    response = _post(ctx, geo_body(CENTRE_LAT, CENTRE_LON, 10))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["building_id"] == ctx.building_id
    assert body["method"] == "geofence"


def test_25m_outside_edge_is_accepted(ctx: Ctx) -> None:
    lat, lon = east_of_edge(25)
    response = _post(ctx, geo_body(lat, lon, 10))
    assert response.status_code == 201, response.text
    assert response.json()["building_id"] == ctx.building_id


def test_40m_outside_edge_is_rejected(ctx: Ctx) -> None:
    lat, lon = east_of_edge(40)
    response = _post(ctx, geo_body(lat, lon, 10))
    assert response.status_code == 403
    assert _type(response) == "urn:floorwars:problem:outside-geofence"


def test_inaccurate_fix_is_rejected(ctx: Ctx) -> None:
    response = _post(ctx, geo_body(CENTRE_LAT, CENTRE_LON, 51))
    assert response.status_code == 403
    assert _type(response) == "urn:floorwars:problem:location-inaccurate"


def test_accuracy_at_limit_and_omitted_are_accepted(ctx: Ctx) -> None:
    assert _post(ctx, geo_body(CENTRE_LAT, CENTRE_LON, 50)).status_code == 201
    assert _post(ctx, geo_body(CENTRE_LAT, CENTRE_LON)).status_code == 201


def test_nearest_building_wins(ctx: Ctx) -> None:
    # Second building 90 m east of the first (centre to centre, edges 50 m apart).
    second = insert_building(ctx.client, CENTRE_LAT, CENTRE_LON + dlon(90))
    # 25 m from the first one's east edge, 25 m from the second one's west edge: pick 20/30.
    lat, lon = east_of_edge(30)  # 30 m from first, 20 m from second
    response = _post(ctx, geo_body(lat, lon, 5))
    assert response.status_code == 201, response.text
    assert response.json()["building_id"] == second


def test_out_of_range_coordinates_are_422(ctx: Ctx) -> None:
    assert _post(ctx, geo_body(91, 0)).status_code == 422
    assert _post(ctx, geo_body(0, 181)).status_code == 422
    assert _post(ctx, geo_body(0, 0, -1)).status_code == 422


def test_unauthenticated_is_401(ctx: Ctx) -> None:
    response = ctx.client.post("/v1/checkins", json=geo_body(CENTRE_LAT, CENTRE_LON))
    assert response.status_code == 401


def test_coordinates_not_echoed_or_stored(ctx: Ctx) -> None:
    lat, lon = 45.74721234, 21.22661234
    response = _post(ctx, geo_body(lat, lon, 12.3456))
    assert response.status_code == 201
    for needle in ("45.7472123", "21.2266123", "12.3456", "latitude", "longitude"):
        assert needle not in response.text
    with ctx.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.execute(text("SELECT to_jsonb(c)::text FROM checkin c")).scalar_one()
    for needle in ("45.7472123", "21.2266123", "12.3456"):
        assert needle not in row


def test_explain_uses_footprint_geography_index(ctx: Ctx) -> None:
    """The geofence predicate must be able to use ix_building_footprint_geog."""
    with ctx.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(text("SET LOCAL enable_seqscan = off"))
        lines = (
            db.execute(
                text(
                    "EXPLAIN SELECT id FROM building WHERE ST_DWithin("
                    "footprint::geography, "
                    "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 30)"
                ),
                {"lat": CENTRE_LAT, "lon": CENTRE_LON},
            )
            .scalars()
            .all()
        )
    plan = "\n".join(lines)
    print(plan)
    assert "ix_building_footprint_geog" in plan
