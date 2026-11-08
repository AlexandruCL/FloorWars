"""Finding 14: rejections are stored up to a per-user hourly cap, and old ones can be purged."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth.ratelimit import Decision
from app.segments import repository, rules
from app.valkey import ValkeyError
from tests.helpers import TEST_DB_URL
from tests.segments.api_world import World, climb, make_world, scalar


@pytest.fixture(autouse=True)
def _leave_database_empty(clean: None) -> Iterator[None]:
    yield
    assert TEST_DB_URL
    engine = create_engine(TEST_DB_URL)
    try:
        with engine.begin() as conn:
            conn.execute(text('TRUNCATE team, season, building, "user" RESTART IDENTITY CASCADE'))
    finally:
        engine.dispose()


class _Limiter:
    """Lets every upload through; allows ``rejections`` hits on ``seg:rej``, or raises."""

    def __init__(self, rejections: int, failure: Exception | None = None) -> None:
        self.left = rejections
        self.failure = failure
        self.rej_calls: list[tuple[str, int, int]] = []

    def hit(self, name: str, subject: str, capacity: int, period_s: int) -> Decision:
        if name != "seg:rej":
            return Decision(allowed=True, retry_after_s=0)
        self.rej_calls.append((subject, capacity, period_s))
        if self.failure:
            raise self.failure
        self.left -= 1
        return Decision(allowed=self.left >= 0, retry_after_s=60)


def _world(make_app: Callable[..., TestClient], limiter: _Limiter) -> World:
    client = make_app()
    world = make_world(client)
    client.app.state.rate_limiter = limiter  # type: ignore[attr-defined]
    return world


def _stored(world: World) -> tuple[int, int, int]:
    return tuple(  # type: ignore[return-value]
        scalar(world.client, f"SELECT count(*) FROM {table}")  # noqa: S608
        for table in ("climb_segment", "segment_receipt", "fraud_flag")
    )


def test_past_the_cap_the_answer_is_the_same_but_nothing_is_stored(
    make_app: Callable[..., TestClient],
) -> None:
    limiter = _Limiter(rejections=2)
    world = _world(make_app, limiter)
    user = world.climber()
    bad = [climb(minutes_ago=i + 1, vert_speed_mps=5.0) for i in range(4)]
    result = user.ok(*bad)
    assert sorted(r["id"] for r in result["rejected"]) == sorted(i["id"] for i in bad)
    assert {r["reason"] for r in result["rejected"]} == {"speed"}
    assert _stored(world) == (2, 2, 2)  # only the two inside the cap
    assert limiter.rej_calls[0] == (str(user.user_id), rules.REJECTED_STORED_PER_HOUR, 3600)


def test_the_cap_never_touches_a_verified_item(make_app: Callable[..., TestClient]) -> None:
    limiter = _Limiter(rejections=0)
    world = _world(make_app, limiter)
    user = world.climber()
    good = climb(minutes_ago=3)
    result = user.ok(climb(minutes_ago=1, vert_speed_mps=5.0), good)
    assert [a["id"] for a in result["accepted"]] == [good["id"]]
    assert result["accepted"][0]["points"] == 60
    assert len(limiter.rej_calls) == 1  # only the rejected item asked the bucket


def test_a_valkey_error_on_the_bucket_stores_nothing_and_keeps_verified_items(
    make_app: Callable[..., TestClient],
) -> None:
    world = _world(make_app, _Limiter(rejections=5, failure=ValkeyError("down")))
    user = world.climber()
    good = climb(minutes_ago=3)
    result = user.ok(climb(minutes_ago=1, vert_speed_mps=5.0), good)
    assert [r["reason"] for r in result["rejected"]] == ["speed"]
    assert [a["id"] for a in result["accepted"]] == [good["id"]]
    assert _stored(world) == (1, 1, 0)  # the verified climb only


def test_purge_rejected_keeps_verified_receipts_and_recent_rows(
    make_app: Callable[..., TestClient],
) -> None:
    world = _world(make_app, _Limiter(rejections=100))
    user = world.climber()
    bad, good = climb(minutes_ago=1, vert_speed_mps=5.0), climb(minutes_ago=3)
    user.ok(bad, good)
    assert _stored(world) == (2, 2, 1)
    now = datetime.now(UTC)
    old = now - timedelta(days=400)
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert repository.purge_rejected(db, now) == (0, 0)  # nothing is old yet
        db.execute(text("UPDATE segment_receipt SET created_at = :t"), {"t": old})
        db.execute(text("UPDATE fraud_flag SET created_at = :t"), {"t": old})
        db.commit()
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert repository.purge_rejected(db, now) == (1, 1)
        db.commit()
    assert _stored(world) == (2, 1, 0)
    assert scalar(world.client, "SELECT status FROM segment_receipt") == "verified"


def test_purge_rejected_flag_ages(make_app: Callable[..., TestClient]) -> None:
    world = _world(make_app, _Limiter(rejections=100))
    user = world.climber()
    user.ok(*(climb(minutes_ago=i + 1, vert_speed_mps=5.0) for i in range(3)))
    now = datetime.now(UTC)
    ages: list[Any] = [(60, True), (60, False), (400, False)]  # (days, resolved)
    with world.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        ids = [r[0] for r in db.execute(text("SELECT id FROM fraud_flag ORDER BY id"))]
        for flag_id, (days, resolved) in zip(ids, ages, strict=True):
            db.execute(
                text("UPDATE fraud_flag SET created_at = :t, resolved_at = :r WHERE id = :i"),
                {"t": now - timedelta(days=days), "r": now if resolved else None, "i": flag_id},
            )
        db.commit()
        assert repository.purge_rejected(db, now)[1] == 2  # resolved and old, unresolved and 400 d
        db.commit()
    assert scalar(world.client, "SELECT count(*) FROM fraud_flag") == 1


def test_after_a_valkey_error_the_batch_stops_calling_valkey(
    make_app: Callable[..., TestClient],
) -> None:
    limiter = _Limiter(rejections=5, failure=ValkeyError("down"))
    world = _world(make_app, limiter)
    user = world.climber()
    result = user.ok(*(climb(minutes_ago=i + 1, vert_speed_mps=5.0) for i in range(4)))
    assert len(result["rejected"]) == 4
    assert len(limiter.rej_calls) == 1  # the batch holds the user's row lock: no more waits


def test_a_stored_rejection_resends_without_a_token_and_the_cap_logs_once_per_batch(
    make_app: Callable[..., TestClient], capsys: pytest.CaptureFixture[str]
) -> None:
    limiter = _Limiter(rejections=1)
    world = _world(make_app, limiter)
    user = world.climber()
    first = climb(minutes_ago=1, vert_speed_mps=5.0)
    extra = [climb(minutes_ago=i + 2, vert_speed_mps=5.0) for i in range(3)]
    user.ok(first)
    assert user.ok(first)["rejected"] == [{"id": first["id"], "reason": "speed"}]
    assert len(limiter.rej_calls) == 1  # the resend came from the receipt
    user.ok(*extra, key="k2")
    out = capsys.readouterr().out
    assert out.count('"rejection cap reached"') == 1
    assert '"capped": 3' in out


def test_a_taken_id_past_the_cap_is_answered_without_a_receipt(
    make_app: Callable[..., TestClient],
) -> None:
    limiter = _Limiter(rejections=0)
    world = _world(make_app, limiter)
    user = world.climber()
    item = climb()
    assert user.ok(item)["accepted"][0]["steps_scored"] == 60
    other = world.second_device(user)
    result = user.ok(item, key="k2", device_id=other)
    assert result["rejected"] == [{"id": item["id"], "reason": "no_checkin"}]
    assert scalar(world.client, "SELECT count(*) FROM segment_receipt") == 1
