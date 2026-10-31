"""Auth: otp_challenge table, user terms and age confirmation timestamps.

Expand-only (plan 7.7): one new table and two nullable columns, nothing dropped or rewritten.
The device registration fields the contract needs (``model``, ``has_barometer``,
``last_seen_at``) already exist in 0001_baseline.

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
    op.add_column("user", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("user", sa.Column("age_confirmed_at", sa.DateTime(timezone=True)))

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
    op.drop_column("user", "age_confirmed_at")
    op.drop_column("user", "terms_accepted_at")
