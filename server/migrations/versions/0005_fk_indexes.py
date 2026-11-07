"""Foreign key indexes: three referencing columns of ``0004_segments`` that had no usable index.

Expand-only (plan 7.7): three new indexes, nothing dropped or rewritten.

- ``ix_climb_segment_checkin_id``: deleting a user cascades to ``checkin``, and the foreign key
  check for each deleted check-in would otherwise scan every partition of ``climb_segment``.
- ``ix_segment_receipt_user_id``, ``ix_fraud_flag_user_id``: the cascades from ``user`` find their
  rows without scanning the table.

``climb_segment`` is partitioned, so its index is created on the parent: PostgreSQL builds one on
every existing partition and every later partition gets its own. ``CONCURRENTLY`` is not possible
on a partitioned parent, so all three are built in the migration's transaction, which blocks
writes to the tables until it commits.

Revision ID: 0005_fk_indexes
Revises: 0004_segments
Create Date: 2026-11-07
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_fk_indexes"
down_revision: str | Sequence[str] | None = "0004_segments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(op.f("ix_climb_segment_checkin_id"), "climb_segment", ["checkin_id"])
    op.create_index(op.f("ix_segment_receipt_user_id"), "segment_receipt", ["user_id"])
    op.create_index(op.f("ix_fraud_flag_user_id"), "fraud_flag", ["user_id"])


def downgrade() -> None:
    """Undo 0005. Only the indexes go; no data is lost."""
    op.drop_index(op.f("ix_fraud_flag_user_id"), table_name="fraud_flag")
    op.drop_index(op.f("ix_segment_receipt_user_id"), table_name="segment_receipt")
    op.drop_index(op.f("ix_climb_segment_checkin_id"), table_name="climb_segment")
