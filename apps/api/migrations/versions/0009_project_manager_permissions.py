"""Reconcile bound-member permissions with the published team sheet."""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0009_project_manager_permissions"
down_revision: str | None = "0008_issue_raci"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _reconcile(include_project_manager=True)


def downgrade() -> None:
    _reconcile(include_project_manager=False)


def _reconcile(*, include_project_manager: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT b.project_id, b.actor_id, b.member_name, v.snapshot "
            "FROM member_bindings b "
            "JOIN projects p ON p.id = b.project_id "
            "JOIN project_versions v ON v.project_id = p.id "
            "AND v.version_number = p.current_version_number "
            "WHERE b.status = 'bound' AND b.actor_id IS NOT NULL"
        )
    ).mappings()
    for row in rows:
        snapshot = row["snapshot"]
        if isinstance(snapshot, str):
            import json

            snapshot = json.loads(snapshot)
        role = _member_role(snapshot, row["member_name"], include_project_manager)
        bind.execute(
            sa.text(
                "UPDATE project_memberships SET role = :role "
                "WHERE project_id = :project_id AND actor_id = :actor_id"
            ),
            {"role": role, "project_id": row["project_id"], "actor_id": row["actor_id"]},
        )


def _member_role(
    snapshot: dict[str, Any], member_name: str, include_project_manager: bool
) -> str:
    member = next(
        (item for item in snapshot.get("members", []) if item.get("name") == member_name),
        None,
    )
    roles = {part.strip() for part in str((member or {}).get("role", "")).split("/")}
    if include_project_manager and (
        (member or {}).get("is_project_manager") is True or "项目经理" in roles
    ):
        return "project_manager"
    assignments = [item.get("assignments", {}) for item in snapshot.get("milestones", [])]
    if any(member_name in item.get("A", []) for item in assignments):
        return "accountable"
    if any(member_name in item.get("R", []) for item in assignments):
        return "responsible"
    return "collaborator"
