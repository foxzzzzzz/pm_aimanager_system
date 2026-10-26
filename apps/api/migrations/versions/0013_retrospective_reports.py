"""Add immutable confirmed retrospective report snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_retrospective_reports"
down_revision: str | None = "0012_milestone_runtime_states"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "retrospective_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("report_number", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("supersedes_report_id", sa.Uuid(), nullable=True),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("review", sa.JSON(), nullable=False),
        sa.Column("facts_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("confirmed_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["supersedes_report_id"], ["retrospective_reports.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "report_number", name="uq_retrospective_project_number"),
    )
    op.create_index("ix_retrospective_reports_project_id", "retrospective_reports", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_retrospective_reports_project_id", table_name="retrospective_reports")
    op.drop_table("retrospective_reports")
