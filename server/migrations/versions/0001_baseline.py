"""Baseline schema: user, device, team, season, team_membership, building, refresh_token.

Hand-written to match app/db/models.py (plan section 5.1; decisions in docs/er_review.md).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column[object]:
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()")
    )


def _created_at() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _user_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id"], ["user.id"], name=op.f(f"fk_{table}_user_id_user"), ondelete="CASCADE"
    )


def upgrade() -> None:
    # Shared extensions: created if missing, never dropped on downgrade (see er_review.md).
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "user",
        _uuid_pk(),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user")),
        sa.UniqueConstraint("email", name=op.f("uq_user_email")),
    )

    op.create_table(
        "device",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("has_barometer", sa.Boolean(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device")),
        _user_fk("device"),
    )
    op.create_index(op.f("ix_device_user_id"), "device", ["user_id"])

    op.create_table(
        "team",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("color_hex", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team")),
        sa.UniqueConstraint("code", name=op.f("uq_team_code")),
        sa.CheckConstraint("color_hex ~ '^#[0-9A-Fa-f]{6}$'", name=op.f("ck_team_color_hex")),
    )

    # `&&` on ranges uses the built-in GiST range opclass; btree_gist is not needed.
    op.create_table(
        "season",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("active_during", postgresql.TSTZRANGE(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_season")),
        sa.CheckConstraint(
            "NOT isempty(active_during)", name=op.f("ck_season_active_during_not_empty")
        ),
        postgresql.ExcludeConstraint(
            (sa.column("active_during"), "&&"), name=op.f("excl_season_active_during"), using="gist"
        ),
    )

    op.create_table(
        "team_membership",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("user_id", "season_id", name=op.f("pk_team_membership")),
        _user_fk("team_membership"),
        sa.ForeignKeyConstraint(
            ["season_id"], ["season.id"], name=op.f("fk_team_membership_season_id_season")
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["team.id"], name=op.f("fk_team_membership_team_id_team")
        ),
    )

    # No floor count or height columns: the game does not need building floor data.
    op.create_table(
        "building",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "footprint",
            Geometry("POLYGON", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_building")),
    )
    op.create_index(
        op.f("ix_building_footprint"), "building", ["footprint"], postgresql_using="gist"
    )

    op.create_table(
        "refresh_token",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        _created_at(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_token")),
        _user_fk("refresh_token"),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_token_token_hash")),
    )
    op.create_index(op.f("ix_refresh_token_user_id"), "refresh_token", ["user_id"])
    op.create_index(op.f("ix_refresh_token_family_id"), "refresh_token", ["family_id"])


def downgrade() -> None:
    # Tables only; the postgis and citext extensions stay (shared, see upgrade()).
    op.drop_table("refresh_token")
    op.drop_table("building")
    op.drop_table("team_membership")
    op.drop_table("season")
    op.drop_table("team")
    op.drop_table("device")
    op.drop_table("user")
