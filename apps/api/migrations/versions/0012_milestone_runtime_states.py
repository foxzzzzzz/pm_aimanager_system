"""Separate milestone runtime state from formal project versions."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0012_milestone_runtime_states"
down_revision: str | None = "0011_issue_delete_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "change_proposals",
        sa.Column(
            "base_runtime_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_table(
        "milestone_runtime_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("milestone_code", sa.String(length=32), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=True),
        sa.Column("schedule_plan_name", sa.String(length=255), nullable=True),
        sa.Column("schedule_revision", sa.Integer(), nullable=False),
        sa.Column("actual_completion", sa.JSON(), nullable=True),
        sa.Column("completion_revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "milestone_code", name="uq_milestone_runtime_project_code"
        ),
    )
    op.create_index(
        op.f("ix_milestone_runtime_states_project_id"),
        "milestone_runtime_states",
        ["project_id"],
        unique=False,
    )
    connection = op.get_bind()
    approved_query = sa.text(
        "SELECT project_id, milestone_code, proposal_kind, base_version_number, "
        "after_value, resolved_at "
        "FROM change_proposals WHERE status = 'approved' "
        "ORDER BY resolved_at, created_at"
    ).columns(
        project_id=sa.Uuid(),
        after_value=sa.JSON(),
        resolved_at=sa.DateTime(timezone=True),
    )
    approved = list(connection.execute(approved_query).mappings())
    current_query = sa.text(
        "SELECT p.id AS project_id, v.snapshot "
        "FROM projects p JOIN project_versions v "
        "ON v.project_id = p.id AND v.version_number = p.current_version_number"
    ).columns(project_id=sa.Uuid(), snapshot=sa.JSON())
    current_snapshots = {
        row["project_id"]: row["snapshot"]
        for row in connection.execute(current_query).mappings()
    }
    current_milestones = {
        project_id: {item.get("code") for item in snapshot.get("milestones", [])}
        for project_id, snapshot in current_snapshots.items()
    }
    version_query = sa.text(
        "SELECT project_id, version_number, snapshot FROM project_versions"
    ).columns(project_id=sa.Uuid(), snapshot=sa.JSON())
    version_plan_names = {
        (row["project_id"], row["version_number"]): row["snapshot"].get("active_plan_name")
        for row in connection.execute(version_query).mappings()
    }
    states: dict[tuple[object, str], dict[str, object]] = {}
    for proposal in approved:
        project_milestones = current_milestones.get(proposal["project_id"], set())
        if proposal["milestone_code"] not in project_milestones:
            continue
        key = (proposal["project_id"], proposal["milestone_code"])
        state = states.setdefault(
            key,
            {
                "id": uuid.uuid4(),
                "project_id": proposal["project_id"],
                "milestone_code": proposal["milestone_code"],
                "schedule": None,
                "schedule_plan_name": None,
                "schedule_revision": 0,
                "actual_completion": None,
                "completion_revision": 0,
                "updated_at": proposal["resolved_at"] or datetime.now(UTC),
            },
        )
        if proposal["proposal_kind"] == "completed":
            state["actual_completion"] = proposal["after_value"]
            state["completion_revision"] = int(state["completion_revision"]) + 1
        else:
            state["schedule"] = proposal["after_value"]
            state["schedule_plan_name"] = version_plan_names.get(
                (proposal["project_id"], proposal["base_version_number"])
            )
            state["schedule_revision"] = int(state["schedule_revision"]) + 1
        state["updated_at"] = proposal["resolved_at"] or state["updated_at"]
    for key, state in list(states.items()):
        snapshot = current_snapshots[state["project_id"]]
        if state["actual_completion"] is not None and _milestone_completion(
            snapshot, str(state["milestone_code"])
        ) != state["actual_completion"]:
            state["actual_completion"] = None
        if state["schedule"] is not None and _plan_window(
            snapshot,
            str(state["milestone_code"]),
            state["schedule_plan_name"],
        ) != state["schedule"]:
            state["schedule"] = None
            state["schedule_plan_name"] = None
        if state["schedule"] is None and state["actual_completion"] is None:
            del states[key]
    if states:
        table = sa.table(
            "milestone_runtime_states",
            sa.column("id", sa.Uuid()),
            sa.column("project_id", sa.Uuid()),
            sa.column("milestone_code", sa.String()),
            sa.column("schedule", sa.JSON()),
            sa.column("schedule_plan_name", sa.String()),
            sa.column("schedule_revision", sa.Integer()),
            sa.column("actual_completion", sa.JSON()),
            sa.column("completion_revision", sa.Integer()),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(table, list(states.values()))


def downgrade() -> None:
    op.drop_index(
        op.f("ix_milestone_runtime_states_project_id"),
        table_name="milestone_runtime_states",
    )
    op.drop_table("milestone_runtime_states")
    op.drop_column("change_proposals", "base_runtime_revision")


def _milestone_completion(snapshot: dict[str, object], milestone_code: str) -> object:
    milestones = snapshot.get("milestones", [])
    if not isinstance(milestones, list):
        return None
    milestone = next(
        (
            item
            for item in milestones
            if isinstance(item, dict) and item.get("code") == milestone_code
        ),
        None,
    )
    return milestone.get("actual_completion") if milestone is not None else None


def _plan_window(
    snapshot: dict[str, object], milestone_code: str, plan_name: object
) -> object:
    milestones = snapshot.get("milestones", [])
    plans = snapshot.get("plan_versions", [])
    if not isinstance(milestones, list) or not isinstance(plans, list):
        return None
    milestone = next(
        (
            item
            for item in milestones
            if isinstance(item, dict) and item.get("code") == milestone_code
        ),
        None,
    )
    plan = next(
        (
            item
            for item in plans
            if isinstance(item, dict) and item.get("name") == plan_name
        ),
        None,
    )
    if milestone is None or plan is None:
        return None
    plan_milestones = plan.get("milestones", {})
    if not isinstance(plan_milestones, dict):
        return None
    return plan_milestones.get(milestone.get("name"))
