"""Landing scans: the ``landing_scan`` table (W4-4, ``POST /v1/landing-scans``).

Expand-only (plan 7.7): one new table with its indexes, nothing existing changes. A scan is worth
``LANDING_SCAN_POINTS``; its points count like a verified segment's (team scores, the 7-day
ownership window by ``scanned_at``, the leaderboards).

- ``ix_landing_scan_building_id_scanned_at``: the owner query (one building, rolling window);
- ``ix_landing_scan_user_id_season_id``: a user's scan points in a season (season-stats);
- ``ix_landing_scan_season_id_team_id``: leaderboard rebuild and fallback reads;
- ``ix_landing_scan_checkin_id``: the foreign key check when a user's check-ins are deleted.

The downgrade drops the table and with it every scan and its points.

Revision ID: 0006_landing_scan
Revises: 0005_fk_indexes
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_landing_scan"
down_revision: str | Sequence[str] | None = "0005_fk_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "landing_scan",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("checkin_id", sa.UUID(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("points >= 0", name=op.f("ck_landing_scan_points_not_negative")),
        sa.ForeignKeyConstraint(
            ["building_id"], ["building.id"], name=op.f("fk_landing_scan_building_id_building")
        ),
        sa.ForeignKeyConstraint(
            ["checkin_id"], ["checkin.id"], name=op.f("fk_landing_scan_checkin_id_checkin")
        ),
        sa.ForeignKeyConstraint(
            ["season_id"], ["season.id"], name=op.f("fk_landing_scan_season_id_season")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["team.id"], name=op.f("fk_landing_scan_team_id_team")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_landing_scan_user_id_user"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_landing_scan")),
    )
    op.create_index(
        "ix_landing_scan_building_id_scanned_at",
        "landing_scan",
        ["building_id", sa.literal_column("scanned_at DESC")],
    )
    op.create_index("ix_landing_scan_user_id_season_id", "landing_scan", ["user_id", "season_id"])
    op.create_index("ix_landing_scan_season_id_team_id", "landing_scan", ["season_id", "team_id"])
    op.create_index("ix_landing_scan_checkin_id", "landing_scan", ["checkin_id"])


def downgrade() -> None:
    """Undo 0006. Drops every landing scan and its points."""
    op.drop_table("landing_scan")
