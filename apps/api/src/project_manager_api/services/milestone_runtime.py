from __future__ import annotations

import copy
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from project_manager_api.db.models import MilestoneRuntimeState


def effective_project_snapshot(
    session: Session, project_id: uuid.UUID, baseline: dict[str, Any]
) -> dict[str, Any]:
    snapshot = copy.deepcopy(baseline)
    states = session.scalars(
        select(MilestoneRuntimeState).where(MilestoneRuntimeState.project_id == project_id)
    )
    milestones = {
        item.get("code"): item for item in snapshot.get("milestones", []) if item.get("code")
    }
    active_plan_name = snapshot.get("active_plan_name")
    active_plan = next(
        (
            plan
            for plan in snapshot.get("plan_versions", [])
            if plan.get("name") == active_plan_name
        ),
        None,
    )
    for state in states:
        milestone = milestones.get(state.milestone_code)
        if milestone is None:
            continue
        if state.actual_completion is not None:
            milestone["actual_completion"] = copy.deepcopy(state.actual_completion)
        if (
            state.schedule is not None
            and state.schedule_plan_name == active_plan_name
            and active_plan is not None
        ):
            milestone_name = milestone.get("name")
            if milestone_name in active_plan.get("milestones", {}):
                active_plan["milestones"][milestone_name] = copy.deepcopy(state.schedule)
    return snapshot


def target_runtime_revision(
    session: Session,
    project_id: uuid.UUID,
    milestone_code: str,
    proposal_kind: str,
) -> int:
    state = session.scalar(
        select(MilestoneRuntimeState).where(
            MilestoneRuntimeState.project_id == project_id,
            MilestoneRuntimeState.milestone_code == milestone_code,
        )
    )
    if state is None:
        return 0
    return (
        state.completion_revision
        if proposal_kind == "completed"
        else state.schedule_revision
    )


def runtime_reset_diff(
    session: Session,
    project_id: uuid.UUID,
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    states = session.scalars(
        select(MilestoneRuntimeState).where(MilestoneRuntimeState.project_id == project_id)
    )
    for state in states:
        if state.actual_completion is not None and (
            _milestone_completion(before, state.milestone_code)
            != _milestone_completion(after, state.milestone_code)
        ):
            changes.append(
                {
                    "path": f"runtime_state[{state.milestone_code}].actual_completion",
                    "operation": "removed",
                    "before": {
                        "value": copy.deepcopy(state.actual_completion),
                        "revision": state.completion_revision,
                    },
                    "after": None,
                }
            )
        if state.schedule is not None and (
            state.schedule_plan_name != after.get("active_plan_name")
            or _plan_window(before, state.milestone_code, state.schedule_plan_name)
            != _plan_window(after, state.milestone_code, state.schedule_plan_name)
        ):
            changes.append(
                {
                    "path": f"runtime_state[{state.milestone_code}].schedule",
                    "operation": "removed",
                    "before": {
                        "value": copy.deepcopy(state.schedule),
                        "plan_name": state.schedule_plan_name,
                        "revision": state.schedule_revision,
                    },
                    "after": None,
                }
            )
    return sorted(changes, key=lambda item: item["path"])


def clear_runtime_overrides(
    session: Session,
    project_id: uuid.UUID,
    changes: list[dict[str, Any]],
) -> None:
    targets: dict[str, set[str]] = {}
    for change in changes:
        path = str(change.get("path", ""))
        if not path.startswith("runtime_state["):
            continue
        milestone_code, field = path.removeprefix("runtime_state[").split("]", maxsplit=1)
        targets.setdefault(milestone_code, set()).add(field.removeprefix("."))
    for milestone_code, fields in targets.items():
        state = session.scalar(
            select(MilestoneRuntimeState).where(
                MilestoneRuntimeState.project_id == project_id,
                MilestoneRuntimeState.milestone_code == milestone_code,
            )
        )
        if state is None:
            continue
        if "schedule" in fields:
            state.schedule = None
            state.schedule_plan_name = None
        if "actual_completion" in fields:
            state.actual_completion = None
        if state.schedule is None and state.actual_completion is None:
            session.delete(state)


def _milestone_completion(snapshot: dict[str, Any], milestone_code: str) -> Any:
    milestone = next(
        (
            item
            for item in snapshot.get("milestones", [])
            if item.get("code") == milestone_code
        ),
        None,
    )
    return copy.deepcopy(milestone.get("actual_completion")) if milestone else None


def _plan_window(
    snapshot: dict[str, Any], milestone_code: str, plan_name: str | None
) -> Any:
    milestone = next(
        (
            item
            for item in snapshot.get("milestones", [])
            if item.get("code") == milestone_code
        ),
        None,
    )
    plan = next(
        (
            item
            for item in snapshot.get("plan_versions", [])
            if item.get("name") == plan_name
        ),
        None,
    )
    if milestone is None or plan is None:
        return None
    return copy.deepcopy(plan.get("milestones", {}).get(milestone.get("name")))
