"""Finding 9: SQL statements run by one 100-item ``POST /v1/segments`` (60 new verified, 25 new
rejected, 15 resends). Lower BASELINE_MAX when the batch gets cheaper."""

from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import Range

from tests.helpers import TEST_DB_URL, TEST_VALKEY_URL
from tests.segments.api_world import World, climb_at, clock_hour, make_world, utcnow

pytestmark = pytest.mark.skipif(not TEST_VALKEY_URL, reason="FLOORWARS_TEST_VALKEY_URL not set")

BASELINE_MAX = 120  # measured 658 before finding 9, 109 after (spec 5a)


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


@pytest.fixture
def world(make_app: Callable[..., TestClient]) -> World:
    return make_world(make_app())


def test_a_mixed_batch_of_100_stays_within_the_statement_budget(world: World) -> None:
    now = utcnow()
    user = world.climber(valid_during=Range(now - timedelta(hours=3), now))
    base = clock_hour(2)

    def at(minute: int, **kw: Any) -> dict[str, Any]:
        return climb_at(base + timedelta(minutes=minute), **kw)

    # Resends: stored by an earlier batch, at minutes 1, 9, 17, ...
    old = [at(1 + 8 * i) for i in range(15)]
    assert len(user.ok(*old, key="first")["accepted"]) == 15
    # 60 verified, 2 minutes apart, 60 steps each: far below 600 steps per 10 minutes.
    verified = [at(2 * i) for i in range(60)]
    bad: list[dict[str, Any]] = [at(31 + 2 * i, steps=500) for i in range(8)]  # steps vs ascent
    bad += [climb_at(now - timedelta(days=30, minutes=i)) for i in range(8)]  # started_at_range
    bad += [{**verified[i], "id": climb_at(now)["id"]} for i in range(9)]  # overlap
    batch = [*verified, *bad, *old]
    assert len(batch) == 100

    engine = world.client.app.state.sessionmaker.kw["bind"]  # type: ignore[attr-defined]
    count = 0

    def tick(*_: Any) -> None:
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", tick)
    try:
        result = user.ok(*batch, key="mixed")
    finally:
        event.remove(engine, "before_cursor_execute", tick)
    print(f"\nBATCH_STATEMENTS={count}")

    reasons = sorted(r["reason"] for r in result["rejected"])
    print(
        "accepted", len(result["accepted"]), "reasons", {r: reasons.count(r) for r in set(reasons)}
    )
    assert len(result["accepted"]) == 60 + 15, result["rejected"][:3]
    assert len(reasons) == 25, reasons
    assert count <= BASELINE_MAX
