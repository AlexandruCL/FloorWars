"""The claim transaction: points, the owner rules, and concurrency on real connections.

The concurrency tests use real threads with separate sessions. They would pass by luck without a
barrier, so each one forces the interleaving that a missing lock would get wrong.
"""

import itertools
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.segments import repository
from app.segments.claim import ROLLING_POINTS_SQL, points_for, recompute_owner, rolling_points
from app.segments.models import STATUS_REJECTED, STATUS_VERIFIED, Flip, SegmentRow
from app.segments.rules import OWNERSHIP_WINDOW
from tests.helpers import TEST_DB_URL

JOIN_TIMEOUT_S = 20
# Long enough for a transaction that should block to reach its lock.
SETTLE_S = 0.5


@dataclass(frozen=True)
class Player:
    user_id: uuid.UUID
    team_id: int
    code: str
    checkin_id: uuid.UUID


@dataclass(frozen=True)
class Arena:
    season_id: int
    building_id: int
    other_building_id: int
    players: dict[str, Player]
    now: datetime


TEAMS = ("AC", "ETC", "MEC")


@pytest.fixture
def engine(clean: None) -> Iterator[Engine]:
    assert TEST_DB_URL
    eng = create_engine(TEST_DB_URL, pool_size=8)
    yield eng
    eng.dispose()


@pytest.fixture
def arena(engine: Engine) -> Arena:
    """Three teams with one player each, in a season, with check-ins at the first building."""
    now = datetime.now(UTC).replace(microsecond=0)
    with Session(engine) as db:
        season_id = db.execute(
            text(
                "INSERT INTO season (active_during) VALUES "
                "(tstzrange(now() - interval '60 days', now() + interval '60 days')) RETURNING id"
            )
        ).scalar_one()
        buildings = [
            db.execute(
                text(
                    "INSERT INTO building (name, footprint) VALUES (:n, "
                    "ST_GeomFromText('POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))', 4326)) RETURNING id"
                ),
                {"n": name},
            ).scalar_one()
            for name in ("Library", "Rectorate")
        ]
        players = {}
        for code in TEAMS:
            team_id = db.execute(
                text("INSERT INTO team (code, color_hex) VALUES (:c, '#112233') RETURNING id"),
                {"c": code},
            ).scalar_one()
            user_id = db.execute(
                text('INSERT INTO "user" (email, display_name) VALUES (:e, :d) RETURNING id'),
                {"e": f"{code.lower()}@student.upt.ro", "d": code},
            ).scalar_one()
            db.execute(
                text(
                    "INSERT INTO team_membership (user_id, season_id, team_id) VALUES (:u, :s, :t)"
                ),
                {"u": user_id, "s": season_id, "t": team_id},
            )
            checkin_id = db.execute(
                text(
                    "INSERT INTO checkin (user_id, building_id, method, valid_during) "
                    "VALUES (:u, :b, 'qr', "
                    "tstzrange(now() - interval '20 days', now() + interval '1 day')) RETURNING id"
                ),
                {"u": user_id, "b": buildings[0]},
            ).scalar_one()
            players[code] = Player(user_id, team_id, code, checkin_id)
        db.commit()
    return Arena(season_id, buildings[0], buildings[1], players, now)


def climb(
    db: Session,
    arena: Arena,
    code: str,
    points: int,
    ago: timedelta = timedelta(minutes=10),
    building_id: int | None = None,
    status: str = STATUS_VERIFIED,
) -> None:
    """Insert one segment worth ``points`` for the team's player, ``ago`` before ``arena.now``."""
    player = arena.players[code]
    verified = status == STATUS_VERIFIED
    repository.insert_segment(
        db,
        SegmentRow(
            id=uuid.uuid4(),
            device_id=uuid.uuid4(),
            user_id=player.user_id,
            team_id=player.team_id,
            season_id=arena.season_id,
            checkin_id=player.checkin_id,
            building_id=building_id or arena.building_id,
            status=status,
            reject_reason=None if verified else "speed",
            steps=max(points, 1),
            steps_scored=max(points, 1) if verified else 0,
            points=points if verified else 0,
            ascent_m=6.0,
            duration_s=30.0,
            vert_speed_mps=0.2,
            stair_prob=0.9,
            classifier_version="rules-1",
            started_at=arena.now - ago,
        ),
    )


def owner(db: Session, arena: Arena, building_id: int | None = None) -> int | None:
    team_id: int | None = db.execute(
        text("SELECT team_id FROM building_claim WHERE season_id = :s AND building_id = :b"),
        {"s": arena.season_id, "b": building_id or arena.building_id},
    ).scalar_one()
    return team_id


def team(arena: Arena, code: str) -> int:
    return arena.players[code].team_id


# Points.


@pytest.mark.parametrize(
    ("steps", "prior", "expected"),
    [
        (1, 0, 1),
        (299, 0, 299),
        (300, 0, 300),
        (301, 0, 300),  # 300 + floor(0.5)
        (302, 0, 301),
        (100, 250, 75),  # 50 full, 50 at half
        (100, 300, 50),
        (100, 500, 50),
        (1, 300, 0),  # floor(0.5)
        (3, 300, 1),
        (2000, 0, 1150),
    ],
)
def test_points_for(steps: int, prior: int, expected: int) -> None:
    assert points_for(steps, prior) == expected


# Owner rules.


def test_first_climb_takes_an_unowned_building(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 40)
        flip = recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        assert flip is not None
        assert (flip.from_team_id, flip.from_code) == (None, None)
        assert (flip.to_team_id, flip.to_code) == (team(arena, "AC"), "AC")
        assert (flip.building_id, flip.season_id, flip.at) == (
            arena.building_id,
            arena.season_id,
            arena.now,
        )
        row = db.execute(
            text(
                "SELECT team_id, claimed_at FROM building_claim "
                "WHERE season_id = :s AND building_id = :b"
            ),
            {"s": arena.season_id, "b": arena.building_id},
        ).one()
        assert (row.team_id, row.claimed_at) == (team(arena, "AC"), arena.now)


def test_flip_writes_one_game_event(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 40)
        recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        climb(db, arena, "ETC", 41)
        flip = recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        assert flip is not None
        assert (flip.from_code, flip.to_code) == ("AC", "ETC")
        events = db.execute(
            text(
                "SELECT id, kind, season_id, building_id, from_team, to_team FROM game_event "
                "ORDER BY id"
            )
        ).all()
        assert len(events) == 2
        last = events[-1]
        assert last.id == flip.event_id
        assert (last.kind, last.season_id, last.building_id) == (
            "building_flipped",
            arena.season_id,
            arena.building_id,
        )
        assert (last.from_team, last.to_team) == (team(arena, "AC"), team(arena, "ETC"))


def test_no_change_returns_none_and_writes_no_event(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 40)
        recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        climbed_at = db.execute(text("SELECT claimed_at FROM building_claim")).scalar_one()
        climb(db, arena, "AC", 5)
        later = arena.now + timedelta(minutes=1)
        assert recompute_owner(db, arena.season_id, arena.building_id, later) is None
        assert db.execute(text("SELECT count(*) FROM game_event")).scalar_one() == 1
        assert db.execute(text("SELECT claimed_at FROM building_claim")).scalar_one() == climbed_at


def test_tie_keeps_the_owner(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 40, ago=timedelta(minutes=5))
        recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        # ETC reached the same total earlier than AC, but AC owns the building.
        climb(db, arena, "ETC", 40, ago=timedelta(minutes=50))
        assert recompute_owner(db, arena.season_id, arena.building_id, arena.now) is None
        assert owner(db, arena) == team(arena, "AC")


def test_one_more_point_flips(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 40)
        recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        climb(db, arena, "ETC", 40)
        assert recompute_owner(db, arena.season_id, arena.building_id, arena.now) is None
        climb(db, arena, "ETC", 1)
        assert recompute_owner(db, arena.season_id, arena.building_id, arena.now) is not None
        assert owner(db, arena) == team(arena, "ETC")


def test_tie_with_no_owner_goes_to_who_reached_it_first(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 40, ago=timedelta(minutes=5))
        climb(db, arena, "ETC", 40, ago=timedelta(minutes=30))
        flip = recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        assert flip is not None
        assert flip.to_code == "ETC"


def test_tie_without_the_owner_goes_to_who_reached_it_first(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "MEC", 10)
        recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        climb(db, arena, "AC", 40, ago=timedelta(minutes=5))
        climb(db, arena, "ETC", 40, ago=timedelta(minutes=30))
        flip = recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        assert flip is not None
        assert (flip.from_code, flip.to_code) == ("MEC", "ETC")


def test_reached_first_compares_the_moment_the_total_was_reached(
    engine: Engine, arena: Arena
) -> None:
    with Session(engine) as db:
        # AC started first but reached 40 only 5 minutes ago; ETC reached it 20 minutes ago.
        climb(db, arena, "AC", 20, ago=timedelta(minutes=60))
        climb(db, arena, "AC", 20, ago=timedelta(minutes=5))
        climb(db, arena, "ETC", 40, ago=timedelta(minutes=20))
        flip = recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        assert flip is not None
        assert flip.to_code == "ETC"


def test_a_zero_point_segment_does_not_delay_reaching_the_total(
    engine: Engine, arena: Arena
) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 40, ago=timedelta(minutes=30))
        climb(db, arena, "AC", 0, ago=timedelta(minutes=1))
        climb(db, arena, "ETC", 40, ago=timedelta(minutes=20))
        standings = rolling_points(db, arena.season_id, arena.building_id, arena.now)
        assert [t.code for t in standings] == ["AC", "ETC"]
        assert standings[0].reached_at == arena.now - timedelta(minutes=30)


def test_exact_tie_in_time_is_decided_the_same_way_every_time(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        same = timedelta(minutes=10)
        climb(db, arena, "ETC", 40, ago=same)
        climb(db, arena, "AC", 40, ago=same)
        flip = recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        assert flip is not None
        assert flip.to_code == "AC"  # the lower team id


def test_window_ageing_lets_a_smaller_score_take_over(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 500, ago=timedelta(days=6, hours=23))
        recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        climb(db, arena, "ETC", 10, ago=timedelta(minutes=1))
        assert recompute_owner(db, arena.season_id, arena.building_id, arena.now) is None
        # Two hours later AC's climb has left the window, ETC's has not.
        later = arena.now + timedelta(hours=2)
        flip = recompute_owner(db, arena.season_id, arena.building_id, later)
        assert flip is not None
        assert (flip.from_code, flip.to_code) == ("AC", "ETC")


def test_window_start_is_inclusive(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 10, ago=timedelta(days=7))
        climb(db, arena, "ETC", 10, ago=timedelta(days=7, seconds=1))
        standings = rolling_points(db, arena.season_id, arena.building_id, arena.now)
        assert [t.code for t in standings] == ["AC"]


def test_owner_stays_when_nobody_has_points_in_the_window(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 10, ago=timedelta(days=1))
        recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        later = arena.now + timedelta(days=30)
        assert recompute_owner(db, arena.season_id, arena.building_id, later) is None
        assert owner(db, arena) == team(arena, "AC")


def test_a_team_with_only_zero_points_does_not_take_a_building(
    engine: Engine, arena: Arena
) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 0)
        assert recompute_owner(db, arena.season_id, arena.building_id, arena.now) is None
        assert owner(db, arena) is None
        assert rolling_points(db, arena.season_id, arena.building_id, arena.now) == []


def test_a_slightly_future_segment_counts_at_once(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 10, ago=timedelta(minutes=-4))
        flip = recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        assert flip is not None


def test_only_verified_segments_of_this_building_and_season_count(
    engine: Engine, arena: Arena
) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 10)
        climb(db, arena, "ETC", 50, status=STATUS_REJECTED)
        climb(db, arena, "MEC", 50, building_id=arena.other_building_id)
        other_season = db.execute(
            text(
                "INSERT INTO season (active_during) VALUES "
                "(tstzrange(now() + interval '90 days', now() + interval '120 days')) RETURNING id"
            )
        ).scalar_one()
        standings = rolling_points(db, arena.season_id, arena.building_id, arena.now)
        assert [(t.code, t.points) for t in standings] == [("AC", 10)]
        assert rolling_points(db, other_season, arena.building_id, arena.now) == []


def test_rolling_points_shape(engine: Engine, arena: Arena) -> None:
    with Session(engine) as db:
        climb(db, arena, "AC", 10, ago=timedelta(minutes=30))
        climb(db, arena, "AC", 15, ago=timedelta(minutes=20))
        climb(db, arena, "ETC", 50, ago=timedelta(minutes=10))
        standings = rolling_points(db, arena.season_id, arena.building_id, arena.now)
    assert [(t.team_id, t.code, t.points) for t in standings] == [
        (team(arena, "ETC"), "ETC", 50),
        (team(arena, "AC"), "AC", 25),
    ]
    assert standings[1].reached_at == arena.now - timedelta(minutes=20)


# Concurrency.


def _run_all(*targets: threading.Thread) -> None:
    for thread in targets:
        thread.start()
    for thread in targets:
        thread.join(JOIN_TIMEOUT_S)
        assert not thread.is_alive(), "a transaction is stuck"


def _upload(
    engine: Engine,
    arena: Arena,
    code: str,
    points: int,
    results: dict[str, object],
    after_insert: threading.Barrier | None = None,
) -> None:
    """One batch: insert, wait for the other batch to have inserted too, recompute, commit."""
    try:
        with Session(engine) as db:
            climb(db, arena, code, points)
            if after_insert is not None:
                after_insert.wait(JOIN_TIMEOUT_S)
            results[code] = recompute_owner(db, arena.season_id, arena.building_id, arena.now)
            db.commit()
    except Exception as exc:  # reported by the test's assertion
        results[code] = exc


def test_two_first_climbs_create_one_claim_and_the_right_owner(
    engine: Engine, arena: Arena
) -> None:
    # Both insert their segment before either recomputes, and neither sees the other's yet. They
    # also race to create the claim row: the loser of that insert must still end up correct.
    for _ in range(5):
        with Session(engine) as db:
            db.execute(text("TRUNCATE climb_segment, building_claim, game_event"))
            db.commit()
        barrier = threading.Barrier(2)
        results: dict[str, object] = {}
        _run_all(
            threading.Thread(target=_upload, args=(engine, arena, "AC", 40, results, barrier)),
            threading.Thread(target=_upload, args=(engine, arena, "ETC", 60, results, barrier)),
        )
        assert not [r for r in results.values() if isinstance(r, Exception)], results
        with Session(engine) as db:
            assert owner(db, arena) == team(arena, "ETC")
            assert db.execute(text("SELECT count(*) FROM building_claim")).scalar_one() == 1
            # The event trail must end at the real owner.
            last_to = db.execute(
                text("SELECT to_team FROM game_event ORDER BY id DESC LIMIT 1")
            ).scalar_one()
            assert last_to == team(arena, "ETC")


def _second_waits_for_first(
    engine: Engine, arena: Arena, first: tuple[str, int], second: tuple[str, int]
) -> tuple[bool, Flip | None]:
    """The first climbs and recomputes, then stays open; the second climbs and recomputes.

    Returns whether the second was still waiting while the first was open, and its flip.
    """
    results: dict[str, Flip | None] = {}
    first_holds_lock = threading.Event()
    first_may_commit = threading.Event()

    def holder() -> None:
        with Session(engine) as db:
            climb(db, arena, *first)
            recompute_owner(db, arena.season_id, arena.building_id, arena.now)
            first_holds_lock.set()
            assert first_may_commit.wait(JOIN_TIMEOUT_S)
            db.commit()

    def challenger() -> None:
        assert first_holds_lock.wait(JOIN_TIMEOUT_S)
        with Session(engine) as db:
            climb(db, arena, *second)
            results["flip"] = recompute_owner(db, arena.season_id, arena.building_id, arena.now)
            db.commit()

    threads = (threading.Thread(target=holder), threading.Thread(target=challenger))
    for thread in threads:
        thread.start()
    assert first_holds_lock.wait(JOIN_TIMEOUT_S)
    threads[1].join(SETTLE_S)
    blocked = threads[1].is_alive()
    first_may_commit.set()
    for thread in threads:
        thread.join(JOIN_TIMEOUT_S)
        assert not thread.is_alive(), "a transaction is stuck"
    return blocked, results["flip"]


def test_two_climbs_that_only_win_together_flip_the_building(engine: Engine, arena: Arena) -> None:
    """Only ``FOR UPDATE`` on the claim guards this case.

    AC's first climb does not flip, so it never updates the claim row and only the row lock can
    make the second wait (``ON CONFLICT`` waits for a writer of the row, not for a row lock).
    Without it each transaction sees 40 points of its own against ETC's 50, and no flip happens
    although AC ends with 80.
    """
    with Session(engine) as db:
        climb(db, arena, "ETC", 50)
        recompute_owner(db, arena.season_id, arena.building_id, arena.now)
        db.commit()
    blocked, flip = _second_waits_for_first(engine, arena, ("AC", 40), ("AC", 40))
    assert blocked, "the second claim did not wait for the first"
    assert flip is not None
    assert (flip.from_code, flip.to_code) == ("ETC", "AC")
    with Session(engine) as db:
        assert owner(db, arena) == team(arena, "AC")


@pytest.mark.parametrize(
    ("first", "second", "second_flip"),
    [
        # The second has more points: it takes the building from the first.
        (("AC", 40), ("ETC", 60), ("AC", "ETC")),
        # The second has fewer: deciding without seeing the first, it would steal the building.
        (("ETC", 60), ("AC", 40), None),
    ],
)
def test_first_two_claims_in_a_building_decide_in_order(
    engine: Engine,
    arena: Arena,
    first: tuple[str, int],
    second: tuple[str, int],
    second_flip: tuple[str, str] | None,
) -> None:
    blocked, flip = _second_waits_for_first(engine, arena, first, second)
    assert blocked, "the second claim did not wait for the first"
    with Session(engine) as db:
        assert owner(db, arena) == team(arena, "ETC")
    assert ((flip.from_code, flip.to_code) if flip else None) == second_flip


def test_many_concurrent_uploads_end_with_the_correct_owner(engine: Engine, arena: Arena) -> None:
    """Many interleaved batches: the claim must equal a recompute from the final segments."""
    errors: list[Exception] = []

    def worker(code: str, points: int) -> None:
        try:
            with Session(engine) as db:
                climb(db, arena, code, points)
                recompute_owner(db, arena.season_id, arena.building_id, arena.now)
                db.commit()
        except Exception as exc:  # reported by the assertion below
            errors.append(exc)

    plan = [("AC", 11), ("ETC", 13), ("MEC", 17)] * 4
    _run_all(*(threading.Thread(target=worker, args=job) for job in plan))
    assert not errors, errors[:1]
    with Session(engine) as db:
        assert owner(db, arena) == team(arena, "MEC")
        # Every flip continues from the previous one; the last ends at the owner.
        flips = db.execute(text("SELECT from_team, to_team FROM game_event ORDER BY id")).all()
        assert flips[0].from_team is None
        for earlier, later in itertools.pairwise(flips):
            assert later.from_team == earlier.to_team
        assert flips[-1].to_team == team(arena, "MEC")


def test_different_buildings_do_not_block_each_other(engine: Engine, arena: Arena) -> None:
    holder_done = threading.Event()
    with Session(engine) as held:
        climb(held, arena, "AC", 40)
        recompute_owner(held, arena.season_id, arena.building_id, arena.now)

        def other_building() -> None:
            with Session(engine) as db:
                climb(db, arena, "ETC", 60, building_id=arena.other_building_id)
                recompute_owner(db, arena.season_id, arena.other_building_id, arena.now)
                db.commit()
            holder_done.set()

        thread = threading.Thread(target=other_building)
        thread.start()
        # The first claim is still open here.
        assert holder_done.wait(JOIN_TIMEOUT_S), "the other building was blocked"
        thread.join(JOIN_TIMEOUT_S)
        held.rollback()


def test_batches_of_one_user_are_serialised_by_the_user_lock(engine: Engine, arena: Arena) -> None:
    """With the user lock, the second batch's hourly steps include the first batch's segment."""
    user_id = arena.players["AC"].user_id
    first_holds_lock = threading.Event()
    first_may_commit = threading.Event()
    seen: dict[str, int] = {}

    def first() -> None:
        with Session(engine) as db:
            assert repository.lock_user(db, user_id)
            climb(db, arena, "AC", 40)
            first_holds_lock.set()
            assert first_may_commit.wait(JOIN_TIMEOUT_S)
            db.commit()

    def second() -> None:
        assert first_holds_lock.wait(JOIN_TIMEOUT_S)
        with Session(engine) as db:
            assert repository.lock_user(db, user_id)
            seen["steps"] = repository.verified_steps_around(
                db, user_id, arena.now, timedelta(hours=1)
            )
            db.commit()

    threads = (threading.Thread(target=first), threading.Thread(target=second))
    for thread in threads:
        thread.start()
    assert first_holds_lock.wait(JOIN_TIMEOUT_S)
    threads[1].join(SETTLE_S)
    blocked = threads[1].is_alive()
    first_may_commit.set()
    for thread in threads:
        thread.join(JOIN_TIMEOUT_S)
        assert not thread.is_alive(), "a transaction is stuck"
    assert blocked, "the second batch did not wait for the user lock"
    assert seen["steps"] == 40


# The plan.


def test_owner_query_uses_the_partial_index(engine: Engine, arena: Arena) -> None:
    player = arena.players["AC"]
    with Session(engine) as db:
        # A busy table: this building is a small part of it. No planner setting is forced, so the
        # test proves the index is chosen on its merits.
        db.execute(
            text(
                "INSERT INTO climb_segment (id, device_id, user_id, team_id, season_id, "
                "checkin_id, building_id, status, reject_reason, steps, steps_scored, points, "
                "ascent_m, duration_s, vert_speed_mps, stair_prob, classifier_version, started_at) "
                "SELECT gen_random_uuid(), gen_random_uuid(), :u, :t, :s, :c, "
                "CASE WHEN n % 100 = 0 THEN :b ELSE :other END, "
                "CASE WHEN n % 10 = 1 THEN 'rejected' ELSE 'verified' END, "
                "CASE WHEN n % 10 = 1 THEN 'speed' END, "
                "40, 40, 40, 6, 30, 0.2, 0.9, 'rules-1', "
                ":now - make_interval(secs => n * 25) FROM generate_series(1, 20000) AS n"
            ),
            {
                "u": player.user_id,
                "t": player.team_id,
                "s": arena.season_id,
                "c": player.checkin_id,
                "b": arena.building_id,
                "other": arena.other_building_id,
                "now": arena.now,
            },
        )
        db.execute(text("ANALYZE climb_segment"))
        plan = list(
            db.execute(
                text("EXPLAIN " + ROLLING_POINTS_SQL.text),
                {
                    "season_id": arena.season_id,
                    "building_id": arena.building_id,
                    "window_start": arena.now - OWNERSHIP_WINDOW,
                },
            ).scalars()
        )
        db.rollback()
    joined = "\n".join(plan)
    assert "building_id_started_at" in joined, joined
    # An empty partition may be scanned sequentially (cost 0); one holding rows may not.
    for line in plan:
        if "Seq Scan on climb_segment" in line:
            assert "cost=0.00..0.00" in line, joined
