"""Add Phase 4 encrypted phone and notification delivery state."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_phase4"
down_revision: str | None = "0004_phase31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("mobile_users") as batch:
        batch.add_column(sa.Column("phone_ciphertext", sa.Text(), nullable=True))
        batch.add_column(sa.Column("phone_key_version", sa.Integer(), nullable=True))

    op.create_table(
        "wechat_subscription_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.String(length=128), nullable=False),
        sa.Column("remaining_uses", sa.Integer(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["mobile_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "template_id", name="uq_wechat_grant_user_template"),
    )
    op.create_index(
        "ix_wechat_subscription_grants_user_id", "wechat_subscription_grants", ["user_id"]
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.String(length=128), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["mobile_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_notification_deliveries_project_id", "notification_deliveries", ["project_id"]
    )
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])
    op.create_index(
        "ix_notification_deliveries_event_type", "notification_deliveries", ["event_type"]
    )
    op.create_index("ix_notification_deliveries_channel", "notification_deliveries", ["channel"])
    with op.batch_alter_table("in_app_messages") as batch:
        batch.add_column(sa.Column("notification_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_in_app_messages_notification_id",
            "notification_deliveries",
            ["notification_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_unique_constraint(
            "uq_in_app_messages_notification_id", ["notification_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("in_app_messages") as batch:
        batch.drop_constraint("uq_in_app_messages_notification_id", type_="unique")
        batch.drop_constraint("fk_in_app_messages_notification_id", type_="foreignkey")
        batch.drop_column("notification_id")
    op.drop_table("notification_deliveries")
    op.drop_table("wechat_subscription_grants")
    with op.batch_alter_table("mobile_users") as batch:
        batch.drop_column("phone_key_version")
        batch.drop_column("phone_ciphertext")
