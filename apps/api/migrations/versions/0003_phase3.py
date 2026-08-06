"""Add Phase 3 mobile identity, binding, and message tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase3"
down_revision: str | None = "0002_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "change_proposals",
        sa.Column("proposal_kind", sa.String(length=32), server_default="schedule", nullable=False),
    )
    op.create_table(
        "mobile_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("openid", sa.String(length=128), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("openid"),
    )
    op.create_table(
        "mobile_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["mobile_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_mobile_sessions_user_id", "mobile_sessions", ["user_id"])
    op.create_table(
        "member_bindings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("member_name", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.String(length=128), nullable=True),
        sa.Column("invitation_token_hash", sa.String(length=64), nullable=False),
        sa.Column("expected_phone", sa.String(length=32), nullable=True),
        sa.Column("provided_phone", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("invitation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["mobile_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "member_name", name="uq_member_binding_project_member"),
        sa.UniqueConstraint("invitation_token_hash"),
    )
    op.create_index("ix_member_bindings_project_id", "member_bindings", ["project_id"])
    op.create_index("ix_member_bindings_user_id", "member_bindings", ["user_id"])
    op.create_index("ix_member_bindings_actor_id", "member_bindings", ["actor_id"])
    op.create_table(
        "in_app_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["mobile_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_in_app_messages_user_id", "in_app_messages", ["user_id"])
    op.create_index("ix_in_app_messages_project_id", "in_app_messages", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_in_app_messages_project_id", table_name="in_app_messages")
    op.drop_index("ix_in_app_messages_user_id", table_name="in_app_messages")
    op.drop_table("in_app_messages")
    op.drop_index("ix_member_bindings_actor_id", table_name="member_bindings")
    op.drop_index("ix_member_bindings_user_id", table_name="member_bindings")
    op.drop_index("ix_member_bindings_project_id", table_name="member_bindings")
    op.drop_table("member_bindings")
    op.drop_index("ix_mobile_sessions_user_id", table_name="mobile_sessions")
    op.drop_table("mobile_sessions")
    op.drop_table("mobile_users")
    op.drop_column("change_proposals", "proposal_kind")
