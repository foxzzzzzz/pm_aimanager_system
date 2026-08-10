"""Add idempotency request fingerprints."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_reliability_hardening"
down_revision: str | None = "0006_change_sets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idempotency_records",
        sa.Column("request_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("idempotency_records", "request_hash")
