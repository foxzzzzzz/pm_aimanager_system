"""Harden Phase 3 authentication, versioning, and phone privacy."""

import copy
import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase31"
down_revision: str | None = "0003_phase3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("project_versions") as batch:
        batch.drop_constraint("uq_project_version_content", type_="unique")
    connection = op.get_bind()
    versions = connection.execute(sa.text("SELECT id, snapshot FROM project_versions"))
    for version in versions.mappings():
        snapshot = version["snapshot"]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        business_snapshot = copy.deepcopy(snapshot)
        business_snapshot.pop("source_sha256", None)
        encoded = json.dumps(
            business_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        connection.execute(
            sa.text("UPDATE project_versions SET content_sha256 = :digest WHERE id = :id"),
            {"digest": digest, "id": version["id"]},
        )

    with op.batch_alter_table("mobile_users") as batch:
        batch.add_column(sa.Column("phone_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("phone_masked", sa.String(length=32), nullable=True))
    op.execute(
        "UPDATE mobile_users SET phone_masked = "
        "CASE WHEN phone IS NULL THEN NULL ELSE "
        "substr(phone, 1, 3) || '****' || substr(phone, length(phone) - 3, 4) END"
    )
    with op.batch_alter_table("mobile_users") as batch:
        batch.drop_column("phone")
        batch.create_index("ix_mobile_users_phone_hash", ["phone_hash"])

    with op.batch_alter_table("member_bindings") as batch:
        batch.add_column(sa.Column("expected_phone_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("expected_phone_masked", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("provided_phone_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("provided_phone_masked", sa.String(length=32), nullable=True))
    op.execute(
        "UPDATE member_bindings SET "
        "expected_phone_masked = CASE WHEN expected_phone IS NULL THEN NULL "
        "ELSE substr(expected_phone, 1, 3) || '****' || "
        "substr(expected_phone, length(expected_phone) - 3, 4) END, "
        "provided_phone_masked = CASE WHEN provided_phone IS NULL THEN NULL "
        "ELSE substr(provided_phone, 1, 3) || '****' || "
        "substr(provided_phone, length(provided_phone) - 3, 4) END"
    )
    op.execute(
        "UPDATE member_bindings SET status = 'revoked', user_id = NULL, actor_id = NULL "
        "WHERE status <> 'bound'"
    )
    op.execute(
        "WITH ranked AS (SELECT id, ROW_NUMBER() OVER ("
        "PARTITION BY project_id, user_id ORDER BY created_at, id) AS position "
        "FROM member_bindings WHERE user_id IS NOT NULL) "
        "UPDATE member_bindings SET status = 'revoked', user_id = NULL, actor_id = NULL "
        "WHERE id IN (SELECT id FROM ranked WHERE position > 1)"
    )
    with op.batch_alter_table("member_bindings") as batch:
        batch.drop_column("expected_phone")
        batch.drop_column("provided_phone")
        batch.create_unique_constraint(
            "uq_member_binding_project_user", ["project_id", "user_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("member_bindings") as batch:
        batch.drop_constraint("uq_member_binding_project_user", type_="unique")
        batch.add_column(sa.Column("provided_phone", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("expected_phone", sa.String(length=32), nullable=True))
        batch.drop_column("provided_phone_masked")
        batch.drop_column("provided_phone_hash")
        batch.drop_column("expected_phone_masked")
        batch.drop_column("expected_phone_hash")

    with op.batch_alter_table("mobile_users") as batch:
        batch.drop_index("ix_mobile_users_phone_hash")
        batch.add_column(sa.Column("phone", sa.String(length=32), nullable=True))
        batch.drop_column("phone_masked")
        batch.drop_column("phone_hash")

    with op.batch_alter_table("project_versions") as batch:
        batch.create_unique_constraint(
            "uq_project_version_content", ["project_id", "content_sha256"]
        )
