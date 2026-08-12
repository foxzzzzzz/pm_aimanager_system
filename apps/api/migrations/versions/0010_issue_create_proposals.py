"""Add approval proposals for new issues."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_issue_create_proposals"
down_revision: str | None = "0009_project_manager_permissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "issue_create_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_by_actor_id", sa.String(length=128), nullable=False),
        sa.Column("resolved_by_actor_id", sa.String(length=128), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("issue_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_issue_create_proposals_project_id"),
        "issue_create_proposals",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_issue_create_proposals_issue_id"),
        "issue_create_proposals",
        ["issue_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_issue_create_proposals_issue_id"), table_name="issue_create_proposals")
    op.drop_index(op.f("ix_issue_create_proposals_project_id"), table_name="issue_create_proposals")
    op.drop_table("issue_create_proposals")
