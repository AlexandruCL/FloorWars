"""Check-in lifecycle: one active check-in per user, constraint, concurrency, migration drift."""

import threading
from datetime import datetime
from typing import Any

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.checkins.conftest import Ctx, qr_body, token_for
from tests.conftest import alembic_config
from tests.helpers import auth_headers, insert_user, new_email

INSERT = text(
    "INSERT INTO checkin (user_id, building_id, method, valid_during) "
    "VALUES (:u, :b, :m, tstzrange(now(), now() + interval '90 minutes'))"
)


def _qr(ctx: Ctx) -> Any:
    return ctx.client.post(
        "/v1/checkins", json=qr_body(token_for(ctx.building_id)), headers=ctx.headers
    )


def test_second_checkin_ends_the_first(ctx: Ctx) -> None:
    first = _qr(ctx)
    second = _qr(ctx)
    assert first.status_code == second.status_code == 201
    with ctx.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        rows = db.execute(
            text(
                "SELECT id::text, lower(valid_during), upper(valid_during) "
                "FROM checkin ORDER BY lower(valid_during)"
            )
        ).all()
    assert [r[0] for r in rows] == [first.json()["id"], second.json()["id"]]
    assert rows[0][2] == rows[1][1]
    # API and database agree on the instants.
    assert datetime.fromisoformat(second.json()["valid_from"]) == rows[1][1]
    assert datetime.fromisoformat(first.json()["valid_until"]) == rows[0][2]
    assert first.json()["valid_until"] == second.json()["valid_from"]


def test_exclusion_constraint_rejects_manual_overlap(ctx: Ctx) -> None:
    params = {"u": ctx.user_id, "b": ctx.building_id, "m": "qr"}
    with ctx.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(INSERT, params)
        db.commit()
        with pytest.raises(IntegrityError, match="excl_checkin_user_overlap"):
            db.execute(INSERT, params)
        db.rollback()
        # Another user may overlap freely.
        other = insert_user(db, new_email())
        db.execute(INSERT, {**params, "u": other})
        db.commit()


def test_empty_range_and_bad_method_rejected(ctx: Ctx) -> None:
    with ctx.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO checkin (user_id, building_id, method, valid_during) "
                    "VALUES (:u, :b, 'qr', 'empty'::tstzrange)"
                ),
                {"u": ctx.user_id, "b": ctx.building_id},
            )
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(INSERT, {"u": ctx.user_id, "b": ctx.building_id, "m": "nfc"})
        db.rollback()


def test_concurrent_checkins_leave_exactly_one_active(ctx: Ctx) -> None:
    n = 8
    barrier = threading.Barrier(n)
    statuses: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        barrier.wait()
        response = _qr(ctx)
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert statuses == [201] * n
    with ctx.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        total, active = db.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE valid_during @> clock_timestamp()) "
                "FROM checkin WHERE user_id = :u"
            ),
            {"u": ctx.user_id},
        ).one()
    assert total == n
    assert active == 1


def test_other_users_checkins_are_independent(ctx: Ctx) -> None:
    with ctx.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        other = insert_user(db, new_email())
    assert _qr(ctx).status_code == 201
    response = ctx.client.post(
        "/v1/checkins",
        json=qr_body(token_for(ctx.building_id)),
        headers=auth_headers(ctx.client.app, other),
    )
    assert response.status_code == 201
    with ctx.client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        active = db.execute(
            text("SELECT count(*) FROM checkin WHERE valid_during @> clock_timestamp()")
        ).scalar_one()
    assert active == 2


def test_alembic_check_is_clean_with_checkin(migrated: None) -> None:
    command.upgrade(alembic_config(), "head")
    command.check(alembic_config())
