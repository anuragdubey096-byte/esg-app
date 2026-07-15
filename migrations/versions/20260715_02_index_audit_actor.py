"""Index audit events by actor for access and incident review.

Revision ID: 20260715_02
Revises: 20260715_01
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260715_02"
down_revision: str | None = "20260715_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_audit_events_actor_user_id"),
        "audit_events",
        ["actor_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_events_actor_user_id"), table_name="audit_events")
