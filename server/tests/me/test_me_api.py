"""``GET /v1/seasons``, ``/v1/me/segments`` and ``/v1/me/season-stats``."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text

from app.me import segments
from app.me.landmarks import LANDMARKS
from tests.helpers import auth_headers
from tests.me.contract import assert_matches
from tests.read.seed import World, add_segment, seed, set_owner

NOW = datetime.now(UTC)


def _headers(client: TestClient, world: World, team: str = "AC") -> dict[str, str]:
    return auth_headers(client.app, world.users[team])  # type: ignore[arg-type]


def _add(client: TestClient, world: World, team: str, points: int = 40, **kw: object) -> None:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        add_segment(db, world, team, 0, points, **kw)  # type: ignore[arg-type]


# --- GET /seasons ---------------------------------------------------------------------------


def test_seasons_newest_first_and_contract_shape(client: TestClient) -> None:
    world = seed(client)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            text(
                "INSERT INTO season (active_during) VALUES (tstzrange("
                "now() - interval '300 days', now() - interval '200 days'))"
            )
        )
        db.commit()
    r = client.get("/v1/seasons", headers=_headers(client, world))
    assert r.status_code == 200
    assert_matches(r.json(), "Season", array=True)
    ids = [s["id"] for s in r.json()]
    assert ids == [world.season_id, world.season_id + 1]  # the active one starts later


def test_seasons_empty_and_401(client: TestClient) -> None:
    world = seed(client)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(text("DELETE FROM team_membership"))
        db.execute(text("DELETE FROM season"))
        db.commit()
    assert client.get("/v1/seasons", headers=_headers(client, world)).json() == []
    assert client.get("/v1/seasons").status_code == 401


# --- GET /me/segments -----------------------------------------------------------------------


def test_segments_shape_reason_and_isolation(client: TestClient) -> None:
    world = seed(client)
    _add(client, world, "AC", started_at=NOW - timedelta(minutes=10))
    _add(client, world, "AC", 0, status="rejected", started_at=NOW - timedelta(minutes=5))
    _add(client, world, "ETC")  # another user's row
    r = client.get("/v1/me/segments", headers=_headers(client, world))
    assert r.status_code == 200
    body = r.json()
    assert_matches(body, "SegmentPage")
    assert body["next_cursor"] is None
    assert [(i["status"], i["reason"]) for i in body["items"]] == [
        ("rejected", "speed"),
        ("verified", None),
    ]
    assert len(body["items"]) == 2  # nothing of ETC's


def test_segments_empty_and_401(client: TestClient) -> None:
    world = seed(client)
    r = client.get("/v1/me/segments", headers=_headers(client, world))
    assert r.json() == {"items": [], "next_cursor": None}
    assert client.get("/v1/me/segments").status_code == 401


def test_segments_paging_is_stable_with_an_insert_between_pages(client: TestClient) -> None:
    world = seed(client)
    for i in range(5):
        _add(client, world, "AC", started_at=NOW - timedelta(minutes=60 - i))
    h = _headers(client, world)
    first = client.get("/v1/me/segments?limit=2", headers=h).json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    _add(client, world, "AC", started_at=NOW)  # newer than everything: must not shift page 2
    second = client.get(f"/v1/me/segments?limit=2&cursor={first['next_cursor']}", headers=h).json()
    third = client.get(f"/v1/me/segments?limit=2&cursor={second['next_cursor']}", headers=h).json()
    assert third["next_cursor"] is None
    seen = [i["id"] for p in (first, second, third) for i in p["items"]]
    assert len(seen) == 5 and len(set(seen)) == 5
    starts = [i["started_at"] for p in (first, second, third) for i in p["items"]]
    assert starts == sorted(starts, reverse=True)


def test_segments_same_started_at_is_not_repeated_or_skipped(client: TestClient) -> None:
    world = seed(client)
    for _ in range(4):
        _add(client, world, "AC", started_at=NOW - timedelta(hours=1))
    h = _headers(client, world)
    seen: list[str] = []
    cursor = ""
    for _ in range(10):  # bounded: a repeating cursor must fail, not hang
        page = client.get(f"/v1/me/segments?limit=1&cursor={cursor}", headers=h).json()
        seen += [i["id"] for i in page["items"]]
        if page["next_cursor"] is None:
            break
        cursor = page["next_cursor"]
    assert len(seen) == 4 and len(set(seen)) == 4


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=x", "cursor=!!!", "cursor=AAAA"])
def test_segments_422(client: TestClient, query: str) -> None:
    world = seed(client)
    r = client.get(f"/v1/me/segments?{query}", headers=_headers(client, world))
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")


def test_segments_query_uses_the_user_index(client: TestClient) -> None:
    world = seed(client)
    _add(client, world, "AC")
    seen: list[tuple[str, object]] = []
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        engine = db.get_bind()
        event.listen(
            engine, "before_cursor_execute", lambda c, cur, st, p, *r: seen.append((st, p))
        )
        segments.page(db, world.users["AC"], 10, segments.encode_cursor(NOW, uuid.uuid4()))
        statement, params = seen[-1]
        db.execute(text("SET LOCAL enable_seqscan = off"))
        plan = " ".join(db.connection().exec_driver_sql("EXPLAIN " + statement, params).scalars())
    assert "_user_id_started_at_idx" in plan and "Seq Scan" not in plan


# --- GET /me/season-stats -------------------------------------------------------------------


def test_stats_shape_totals_rank_and_buildings(client: TestClient) -> None:
    world = seed(client)
    _add(client, world, "AC", 100)
    _add(client, world, "AC", 20, started_at=NOW - timedelta(hours=2))
    _add(client, world, "AC", 0, status="rejected", started_at=NOW - timedelta(hours=3))
    _add(client, world, "ETC", 500)  # ahead of AC
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        set_owner(db, world, "AC", 0)
    r = client.get("/v1/me/season-stats", headers=_headers(client, world))
    assert r.status_code == 200
    body = r.json()
    assert_matches(body, "SeasonStats")
    assert body["season_id"] == world.season_id
    assert body["team_id"] == world.team_ids["AC"]
    assert (body["steps_verified"], body["ascent_m"], body["points"]) == (80, 12.0, 120)
    assert body["rank"] == 2
    assert body["buildings_owned_by_team"] == 1


def test_stats_without_points_or_team(client: TestClient) -> None:
    world = seed(client)
    r = client.get("/v1/me/season-stats", headers=_headers(client, world))
    assert r.json()["rank"] is None and r.json()["points"] == 0
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(text("DELETE FROM team_membership WHERE user_id = :u"), {"u": world.users["AC"]})
        db.commit()
    body = client.get("/v1/me/season-stats", headers=_headers(client, world)).json()
    assert body["team_id"] is None and body["buildings_owned_by_team"] == 0
    assert_matches(body, "SeasonStats")


def test_stats_season_default_and_explicit(client: TestClient) -> None:
    world = seed(client)
    _add(client, world, "AC", 100)
    h = _headers(client, world)
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        old = db.execute(
            text(
                "INSERT INTO season (active_during) VALUES (tstzrange("
                "now() - interval '300 days', now() - interval '200 days')) RETURNING id"
            )
        ).scalar_one()
        db.commit()
    assert client.get("/v1/me/season-stats", headers=h).json()["season_id"] == world.season_id
    other = client.get(f"/v1/me/season-stats?season_id={old}", headers=h).json()
    assert other["season_id"] == old and other["points"] == 0 and other["team_id"] is None


def test_stats_404_unknown_and_no_active_season(client: TestClient) -> None:
    world = seed(client, active=False)
    h = _headers(client, world)
    for query in ("", "?season_id=99999"):
        r = client.get(f"/v1/me/season-stats{query}", headers=h)
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/problem+json")
    ok = client.get(f"/v1/me/season-stats?season_id={world.season_id}", headers=h)
    assert ok.status_code == 200


@pytest.mark.parametrize("query", ["season_id=0", "season_id=x"])
def test_stats_422_and_401(client: TestClient, query: str) -> None:
    world = seed(client)
    r = client.get(f"/v1/me/season-stats?{query}", headers=_headers(client, world))
    assert r.status_code == 422
    assert client.get("/v1/me/season-stats").status_code == 401


def test_stats_database_fallback_without_valkey(make_app) -> None:  # type: ignore[no-untyped-def]
    client = make_app(valkey_url=None)
    world = seed(client)
    _add(client, world, "AC", 100)
    _add(client, world, "ETC", 500)
    assert client.get("/v1/me/season-stats", headers=_headers(client, world)).json()["rank"] == 2


def test_landmark_boundary_is_reached(client: TestClient) -> None:
    world = seed(client)
    h = _headers(client, world)
    name, height, _ = LANDMARKS[0]
    _add(client, world, "AC", started_at=NOW - timedelta(minutes=60))
    _add(client, world, "AC", started_at=NOW - timedelta(minutes=10))

    def set_second(ascent: float) -> list[dict[str, object]]:
        with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            db.execute(text("UPDATE climb_segment SET ascent_m = 50"))
            db.execute(
                text(
                    "UPDATE climb_segment SET ascent_m = :a "
                    "WHERE started_at > now() - interval '30 minutes'"
                ),
                {"a": ascent},
            )
            db.commit()
        return client.get("/v1/me/season-stats", headers=h).json()["landmarks"]  # type: ignore[no-any-return]

    assert set_second(43.0)[0] == {"name": name, "height_m": height, "reached": True}
    assert set_second(42.99)[0]["reached"] is False
    assert [m["height_m"] for m in set_second(43.0)] == sorted(m[1] for m in LANDMARKS)


def _scan(client: TestClient, world: World, team: str, points: int) -> None:
    """A landing scan of ``team``'s user at building 0 (its check-in comes from ``_add``)."""
    building_id = world.building_ids[0]
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            text(
                "INSERT INTO landing_scan (user_id, building_id, season_id, team_id, checkin_id, "
                "points, scanned_at) VALUES (:u, :b, :s, :t, :c, :p, now())"
            ),
            {
                "u": world.users[team],
                "b": building_id,
                "s": world.season_id,
                "t": world.team_ids[team],
                "c": world.checkins[(team, building_id)],
                "p": points,
            },
        )
        db.commit()


@pytest.mark.parametrize("valkey", [True, False], ids=["valkey", "database"])
def test_stats_count_landing_scan_points(make_app, valkey: bool) -> None:  # type: ignore[no-untyped-def]
    """Scan points add to ``points`` and ``rank``, never to ``steps_verified`` or ``ascent_m``."""
    client = make_app() if valkey else make_app(valkey_url=None)
    world = seed(client)
    _add(client, world, "AC", 100)
    _add(client, world, "ETC", 500)
    _scan(client, world, "AC", 450)  # 550 > 500: AC overtakes ETC only with its scan points
    body = client.get("/v1/me/season-stats", headers=_headers(client, world)).json()
    assert (body["steps_verified"], body["ascent_m"], body["points"]) == (40, 6.0, 550)
    assert body["rank"] == 1
    etc = client.get("/v1/me/season-stats", headers=_headers(client, world, "ETC")).json()
    assert etc["rank"] == 2
