"""Add RACI assignments to issues."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_issue_raci"
down_revision: str | None = "0007_reliability_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("issues", sa.Column("accountable_names", sa.JSON(), nullable=True))
    op.add_column("issues", sa.Column("consulted_names", sa.JSON(), nullable=True))
    op.add_column("issues", sa.Column("informed_names", sa.JSON(), nullable=True))
    dialect = op.get_bind().dialect.name
    accountable = (
        "json_build_array(owner_name)" if dialect == "postgresql" else "json_array(owner_name)"
    )
    op.execute(
        f"UPDATE issues SET accountable_names = {accountable}, "
        "consulted_names = '[]', informed_names = '[]'"
    )
    with op.batch_alter_table("issues") as batch_op:
        batch_op.alter_column("accountable_names", nullable=False)
        batch_op.alter_column("consulted_names", nullable=False)
        batch_op.alter_column("informed_names", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("issues") as batch_op:
        batch_op.drop_column("informed_names")
        batch_op.drop_column("consulted_names")
        batch_op.drop_column("accountable_names")
