"""Add versioned project data change sets."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_change_sets"
down_revision: str | None = "0005_phase4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_change_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("base_version_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("operations", sa.JSON(), nullable=False),
        sa.Column("diff", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submitted_by_actor_id", sa.String(length=128), nullable=False),
        sa.Column("published_by_actor_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_project_change_sets_project_id", "project_change_sets", ["project_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_project_change_sets_project_id", table_name="project_change_sets")
    op.drop_table("project_change_sets")
