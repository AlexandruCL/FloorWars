"""Queries for teams, seasons and memberships. No business rules here."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Season, Team, TeamMembership

UNIQUE_VIOLATION = "23505"


def list_teams(db: Session) -> list[Team]:
    return list(db.scalars(select(Team).order_by(Team.code)))


def get_team(db: Session, team_id: int) -> Team | None:
    return db.get(Team, team_id)


def get_season(db: Session, season_id: int) -> Season | None:
    return db.get(Season, season_id)


def active_season(db: Session) -> Season | None:
    """The season whose ``active_during`` contains the database's now (ranges do not overlap)."""
    return db.scalars(select(Season).where(Season.active_during.contains(func.now()))).first()


def is_active(db: Session, season_id: int) -> bool:
    found = db.scalar(
        select(Season.id).where(Season.id == season_id, Season.active_during.contains(func.now()))
    )
    return found is not None


def add_membership(db: Session, user_id: uuid.UUID, season_id: int, team_id: int) -> bool:
    """Insert and commit the membership; False if the user already has one for the season.

    The primary key ``(user_id, season_id)`` is the guarantee, so concurrent joins are safe.
    """
    db.add(TeamMembership(user_id=user_id, season_id=season_id, team_id=team_id))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION:
            return False
        raise
    return True
