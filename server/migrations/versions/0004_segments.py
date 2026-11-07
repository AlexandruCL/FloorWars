"""Segments: climb_segment (partitioned), receipts, fraud flags, scores, claims, game events.

Expand-only (plan 7.7): new tables only, nothing dropped or rewritten.

- ``climb_segment``: range-partitioned by month on ``started_at``, so the primary key has to be
  ``(id, started_at)``. Partitions are created here and afterwards by
  ``python -m app.segments.partitions``. There is no default partition.
- ``segment_receipt``: decides resends per ``(device_id, id)``; a unique key on the partitioned
  table could not, as it would have to include ``started_at``.
- ``fraud_flag``: no foreign key to ``climb_segment``, so a partition drop is never blocked.
- ``team_building_score``: season totals. ``building_claim``: owner, the row the claim locks.
- ``game_event``: written inside the claim transaction (plan 7.2.1).

Revision ID: 0004_segments
Revises: 0003_checkin
Create Date: 2026-11-07
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_segments"
down_revision: str | Sequence[str] | None = "0003_checkin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _month_start(year: int, month_index: int) -> datetime:
    """UTC start of the month ``month_index`` months after January of ``year`` (may be negative)."""
    years, month = divmod(month_index, 12)
    return datetime(year + years, month + 1, 1, tzinfo=UTC)


def _create_partitions() -> None:
    # Frozen copy of app.segments.partitions.ensure_partitions (migrations never import app code
    # that can change). The previous month is included because a segment may be 7 days old.
    now = datetime.now(UTC)
    first = now.month - 1
    for index in range(first - 1, first + 3):
        start, end = _month_start(now.year, index), _month_start(now.year, index + 1)
        # Dates generated above; DDL takes no bound parameters.
        op.execute(
            f"CREATE TABLE IF NOT EXISTS climb_segment_{start:%Y%m} PARTITION OF climb_segment "
            f"FOR VALUES FROM ('{start:%Y-%m-%d} 00:00:00+00') TO ('{end:%Y-%m-%d} 00:00:00+00')"
        )


def upgrade() -> None:
    op.create_table(
        "climb_segment",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("checkin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column("steps_scored", sa.SmallInteger(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("ascent_m", sa.REAL(), nullable=False),
        sa.Column("duration_s", sa.REAL(), nullable=False),
        sa.Column("vert_speed_mps", sa.REAL(), nullable=False),
        sa.Column("stair_prob", sa.REAL(), nullable=False),
        sa.Column("classifier_version", sa.Text(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", "started_at", name=op.f("pk_climb_segment")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_climb_segment_user_id_user"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["team.id"], name=op.f("fk_climb_segment_team_id_team")
        ),
        sa.ForeignKeyConstraint(
            ["season_id"], ["season.id"], name=op.f("fk_climb_segment_season_id_season")
        ),
        sa.ForeignKeyConstraint(
            ["checkin_id"], ["checkin.id"], name=op.f("fk_climb_segment_checkin_id_checkin")
        ),
        sa.ForeignKeyConstraint(
            ["building_id"], ["building.id"], name=op.f("fk_climb_segment_building_id_building")
        ),
        sa.CheckConstraint(
            "status IN ('verified', 'rejected')", name=op.f("ck_climb_segment_status")
        ),
        sa.CheckConstraint(
            "steps_scored BETWEEN 0 AND 2000", name=op.f("ck_climb_segment_steps_scored_range")
        ),
        sa.CheckConstraint("points >= 0", name=op.f("ck_climb_segment_points_not_negative")),
        sa.CheckConstraint(
            "status = 'rejected' OR (steps BETWEEN 1 AND 2000 "
            "AND ascent_m BETWEEN 2.0 AND 120.0 AND stair_prob BETWEEN 0 AND 1)",
            name=op.f("ck_climb_segment_verified_bounds"),
        ),
        sa.CheckConstraint(
            "(status = 'rejected') = (reject_reason IS NOT NULL)",
            name=op.f("ck_climb_segment_reject_reason_if_rejected"),
        ),
        postgresql_partition_by="RANGE (started_at)",
    )
    op.create_index(
        op.f("ix_climb_segment_building_id_started_at"),
        "climb_segment",
        ["building_id", sa.text("started_at DESC")],
        postgresql_where=sa.text("status = 'verified'"),
    )
    op.create_index(
        op.f("ix_climb_segment_user_id_started_at"),
        "climb_segment",
        ["user_id", sa.text("started_at DESC")],
    )
    op.create_index(
        op.f("ix_climb_segment_season_id_team_id"), "climb_segment", ["season_id", "team_id"]
    )
    _create_partitions()

    op.create_table(
        "segment_receipt",
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("steps_scored", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("device_id", "id", name=op.f("pk_segment_receipt")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name=op.f("fk_segment_receipt_user_id_user"),
            ondelete="CASCADE",
        ),
    )

    op.create_table(
        "fraud_flag",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("segment_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fraud_flag")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_fraud_flag_user_id_user"), ondelete="CASCADE"
        ),
    )
    op.create_index(
        op.f("ix_fraud_flag_created_at"),
        "fraud_flag",
        ["created_at"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )

    op.create_table(
        "team_building_score",
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("steps", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.PrimaryKeyConstraint(
            "season_id", "building_id", "team_id", name=op.f("pk_team_building_score")
        ),
        sa.ForeignKeyConstraint(
            ["season_id"], ["season.id"], name=op.f("fk_team_building_score_season_id_season")
        ),
        sa.ForeignKeyConstraint(
            ["building_id"],
            ["building.id"],
            name=op.f("fk_team_building_score_building_id_building"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["team.id"], name=op.f("fk_team_building_score_team_id_team")
        ),
        sa.CheckConstraint("points >= 0", name=op.f("ck_team_building_score_points_not_negative")),
    )

    op.create_table(
        "building_claim",
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("season_id", "building_id", name=op.f("pk_building_claim")),
        sa.ForeignKeyConstraint(
            ["season_id"], ["season.id"], name=op.f("fk_building_claim_season_id_season")
        ),
        sa.ForeignKeyConstraint(
            ["building_id"], ["building.id"], name=op.f("fk_building_claim_building_id_building")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["team.id"], name=op.f("fk_building_claim_team_id_team")
        ),
    )

    op.create_table(
        "game_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=True),
        sa.Column("building_id", sa.Integer(), nullable=True),
        sa.Column("from_team", sa.Integer(), nullable=True),
        sa.Column("to_team", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_game_event")),
        sa.CheckConstraint(
            "kind IN ('building_flipped', 'season_state')", name=op.f("ck_game_event_kind")
        ),
    )
    op.create_index(op.f("ix_game_event_created_at"), "game_event", ["created_at"])


def downgrade() -> None:
    """Undo 0004. Destroys data: every segment, receipt, flag, score, claim and event."""
    op.drop_table("game_event")
    op.drop_table("building_claim")
    op.drop_table("team_building_score")
    op.drop_table("fraud_flag")
    op.drop_table("segment_receipt")
    op.drop_table("climb_segment")  # takes all its partitions with it
