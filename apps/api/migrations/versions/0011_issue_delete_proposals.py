"""Add approval proposals for issue deletion."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_issue_delete_proposals"
down_revision: str | None = "0010_issue_create_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "issue_delete_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("issue_id", sa.Uuid(), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_by_actor_id", sa.String(length=128), nullable=False),
        sa.Column("resolved_by_actor_id", sa.String(length=128), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["issue_id"], ["issues.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_issue_delete_proposals_project_id"),
        "issue_delete_proposals",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_issue_delete_proposals_issue_id"),
        "issue_delete_proposals",
        ["issue_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_issue_delete_proposals_issue_id"), table_name="issue_delete_proposals")
    op.drop_index(op.f("ix_issue_delete_proposals_project_id"), table_name="issue_delete_proposals")
    op.drop_table("issue_delete_proposals")
