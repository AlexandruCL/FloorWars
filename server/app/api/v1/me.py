"""``GET /v1/me/segments``, ``/v1/me/season-stats``, ``/v1/me/export`` and ``DELETE /v1/me``.

Problem types (404): ``season-not-found``, ``no-active-season``. ``pending`` is never returned
(pending rows live on the phone). Rejected segments past the 200-per-hour cap are not stored, so
the history cannot show them.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from app.api.deps import CurrentUser, DbSession, Limiter
from app.api.problems import problem_doc
from app.constants import MAX_ID
from app.me import gdpr, segments, stats
from app.teams import service as teams_service
from app.valkey import ValkeyClient

router = APIRouter(tags=["me"])


class SegmentRecordOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    checkin_id: uuid.UUID
    started_at: datetime
    building_id: int
    ascent_m: float
    duration_s: float
    vert_speed_mps: float
    steps: int
    stair_prob: float
    classifier_version: str
    status: Literal["verified", "rejected"]
    steps_scored: int
    reason: str | None


class SegmentPageOut(BaseModel):
    items: list[SegmentRecordOut]
    next_cursor: str | None


class LandmarkOut(BaseModel):
    name: str
    height_m: float
    reached: bool


class SeasonStatsOut(BaseModel):
    season_id: int
    team_id: int | None
    steps_verified: int
    ascent_m: float
    points: int
    rank: int | None
    buildings_owned_by_team: int
    landmarks: list[LandmarkOut]


@router.get(
    "/me/segments",
    response_model=SegmentPageOut,
    responses={
        401: problem_doc("Missing or invalid access token."),
        422: problem_doc("Bad ``limit`` or ``cursor``."),
    },
    operation_id="listMySegments",
)
def list_my_segments(
    user: CurrentUser,
    db: DbSession,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SegmentPageOut:
    """The caller's stored segments, newest ``started_at`` first."""
    rows, next_cursor = segments.page(db, user.id, limit, cursor or None)
    return SegmentPageOut(
        items=[
            SegmentRecordOut(
                id=r.id,
                checkin_id=r.checkin_id,
                started_at=r.started_at,
                building_id=r.building_id,
                ascent_m=r.ascent_m,
                duration_s=r.duration_s,
                vert_speed_mps=r.vert_speed_mps,
                steps=r.steps,
                stair_prob=r.stair_prob,
                classifier_version=r.classifier_version,
                status=r.status,  # type: ignore[arg-type]
                steps_scored=r.steps_scored,
                reason=r.reject_reason,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
    )


@router.get(
    "/me/season-stats",
    response_model=SeasonStatsOut,
    responses={
        401: problem_doc("Missing or invalid access token."),
        404: problem_doc(
            "Unknown ``season_id`` (``season-not-found``), or none given and no season is active "
            "(``no-active-season``)."
        ),
        422: problem_doc("Bad ``season_id``."),
    },
    operation_id="getSeasonStats",
)
def get_season_stats(
    request: Request,
    user: CurrentUser,
    db: DbSession,
    season_id: Annotated[int | None, Query(ge=1, le=MAX_ID)] = None,
) -> SeasonStatsOut:
    """Totals, rank, the team's buildings and landmarks progress for one season."""
    if season_id is None:
        season_id = teams_service.active_season(db).id
    else:
        teams_service.require_season(db, season_id)
    vk: ValkeyClient | None = getattr(request.app.state, "valkey", None)
    return SeasonStatsOut.model_validate(stats.stats(db, vk, user.id, season_id))


@router.get(
    "/me/export",
    responses={
        401: problem_doc("Missing or invalid access token."),
        429: problem_doc("More than 3 exports in an hour."),
        503: problem_doc("The rate limiter is unavailable."),
    },
    operation_id="exportMyData",
)
def export_my_data(user: CurrentUser, db: DbSession, limiter: Limiter) -> dict[str, object]:
    """Everything stored about the caller (``MyDataExport``)."""
    gdpr.take_export_token(limiter, user.id)
    return gdpr.export_user(db, user.id)


@router.delete(
    "/me",
    status_code=204,
    response_class=Response,
    responses={401: problem_doc("Missing or invalid access token.")},
    operation_id="deleteMe",
)
def delete_me(request: Request, user: CurrentUser, db: DbSession) -> Response:
    """Delete the caller's account (``app.me.gdpr.delete_user``)."""
    gdpr.delete_user(db, request.app.state.valkey, user.id, datetime.now(UTC))
    return Response(status_code=204)
