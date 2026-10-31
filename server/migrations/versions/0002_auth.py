"""Auth: otp_challenge table, user terms and age confirmation timestamps.

Mostly expand-only (plan 7.7): one new table and nullable columns. One reshaping change, made
before 0002 was ever deployed (the VM runs 0001 with no devices): ``device`` gets the composite
primary key ``(user_id, id)`` so a device id is unique per user only and sign-in never moves a
device between users; the separate ``ix_device_user_id`` index becomes redundant (the key leads
with ``user_id``) and is dropped. The device registration fields the contract needs (``model``,
``has_barometer``, ``last_seen_at``) already exist in 0001_baseline.

Revision ID: 0002_auth
Revises: 0001_baseline
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_auth"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("pk_device", "device", type_="primary")
    op.create_primary_key("pk_device", "device", ["user_id", "id"])
    op.drop_index("ix_device_user_id", table_name="device")

    op.add_column("user", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("user", sa.Column("age_confirmed_at", sa.DateTime(timezone=True)))
    op.add_column("refresh_token", sa.Column("rotated_at", sa.DateTime(timezone=True)))

    op.create_table(
        "otp_challenge",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("code_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("salt", postgresql.BYTEA(), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_otp_challenge")),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 5", name=op.f("ck_otp_challenge_attempts_range")
        ),
    )
    # At most one active challenge per e-mail; also the lookup index for verify.
    op.create_index(
        op.f("ix_otp_challenge_email"),
        "otp_challenge",
        ["email"],
        unique=True,
        postgresql_where=sa.text("consumed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("otp_challenge")
    # Fails if two users registered the same device id; delete the duplicates first.
    op.create_index("ix_device_user_id", "device", ["user_id"])
    op.drop_constraint("pk_device", "device", type_="primary")
    op.create_primary_key("pk_device", "device", ["id"])
    op.drop_column("refresh_token", "rotated_at")
    op.drop_column("user", "age_confirmed_at")
    op.drop_column("user", "terms_accepted_at")
