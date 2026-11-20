"""SQL of the landing scan. No commits here: ``app.landing.service`` owns the transaction."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, insert, literal, select
from sqlalchemy.orm import Session

from app.db.models import Checkin, LandingScan, Season, TeamMembership


@dataclass(frozen=True, slots=True)
class ScanContext:
    """The user's check-in at the building valid at the scan time, that time's season and the
    user's team in it; each ``None`` when missing."""

    checkin_id: uuid.UUID | None
    season_id: int | None
    team_id: int | None


def scan_context(db: Session, user_id: uuid.UUID, building_id: int, at: datetime) -> ScanContext:
    """One row: the anchor keeps it when an outer join finds nothing. The exclusion constraints
    allow at most one check-in per user and one season at ``at``."""
    anchor = select(literal(1).label("one")).subquery("anchor")
    row = db.execute(
        select(Checkin.id, Season.id.label("season_id"), TeamMembership.team_id)
        .select_from(anchor)
        .outerjoin(
            Checkin,
            and_(
                Checkin.user_id == user_id,
                Checkin.building_id == building_id,
                Checkin.valid_during.contains(at),
            ),
        )
        .outerjoin(Season, Season.active_during.contains(at))
        .outerjoin(
            TeamMembership,
            and_(TeamMembership.user_id == user_id, TeamMembership.season_id == Season.id),
        )
    ).one()
    return ScanContext(row.id, row.season_id, row.team_id)


def insert_scan(
    db: Session,
    user_id: uuid.UUID,
    building_id: int,
    ctx: ScanContext,
    points: int,
    scanned_at: datetime,
) -> uuid.UUID:
    scan_id: uuid.UUID = db.execute(
        insert(LandingScan)
        .values(
            user_id=user_id,
            building_id=building_id,
            season_id=ctx.season_id,
            team_id=ctx.team_id,
            checkin_id=ctx.checkin_id,
            points=points,
            scanned_at=scanned_at,
        )
        .returning(LandingScan.id)
    ).scalar_one()
    return scan_id


def scan_points(db: Session, user_id: uuid.UUID, season_id: int) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(LandingScan.points), 0)).where(
                LandingScan.user_id == user_id, LandingScan.season_id == season_id
            )
        )
        or 0
    )
