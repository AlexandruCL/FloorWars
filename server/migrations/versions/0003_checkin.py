"""Check-in: checkin table, geography index on building footprints.

Expand-only (plan 7.7): one new table and one new index, nothing dropped or rewritten.

- ``checkin``: one row per check-in, valid for ``valid_during`` (90 minutes by default). The
  exclusion constraint ``excl_checkin_user_overlap`` guarantees that the check-ins of one user
  never overlap, so a user has at most one active check-in. ``user_id WITH =`` in a GiST index
  needs ``btree_gist``. No coordinates are stored (plan 8: location only at check-in).
- ``ix_building_footprint_geog``: functional GiST index on ``(footprint::geography)``, used by
  the geofence lookup (``ST_DWithin`` in metres on the geography type).

Revision ID: 0003_checkin
Revises: 0002_auth
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_checkin"
down_revision: str | Sequence[str] | None = "0002_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # On the VM the extension is created by hand as postgres first (the migrator role cannot);
    # IF NOT EXISTS keeps this a no-op there. Shared, never dropped on downgrade.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "checkin",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("valid_during", postgresql.TSTZRANGE(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_checkin")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_checkin_user_id_user"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["building_id"], ["building.id"], name=op.f("fk_checkin_building_id_building")
        ),
        sa.CheckConstraint("method IN ('qr', 'geofence')", name=op.f("ck_checkin_method")),
        sa.CheckConstraint(
            "NOT isempty(valid_during)", name=op.f("ck_checkin_valid_during_not_empty")
        ),
        postgresql.ExcludeConstraint(
            (sa.column("user_id"), "="),
            (sa.column("valid_during"), "&&"),
            name=op.f("excl_checkin_user_overlap"),
            using="gist",
        ),
    )
    op.create_index(op.f("ix_checkin_building_id"), "checkin", ["building_id"])

    op.create_index(
        op.f("ix_building_footprint_geog"),
        "building",
        [sa.text("(footprint::geography)")],
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_building_footprint_geog"), table_name="building")
    op.drop_table("checkin")
    # btree_gist stays (shared extension, see upgrade()).
