from typing import Any

from project_manager_api.db.models import ProjectRole


def member_role(snapshot: dict[str, Any], member_name: str) -> str:
    member = next(
        (item for item in snapshot.get("members", []) if item.get("name") == member_name),
        None,
    )
    if member and (
        member.get("is_project_manager") is True
        or "项目经理" in {part.strip() for part in str(member.get("role", "")).split("/")}
    ):
        return ProjectRole.MANAGER
    assignments = [item.get("assignments", {}) for item in snapshot.get("milestones", [])]
    if any(member_name in item.get("A", []) for item in assignments):
        return ProjectRole.ACCOUNTABLE
    if any(member_name in item.get("R", []) for item in assignments):
        return ProjectRole.RESPONSIBLE
    return ProjectRole.COLLABORATOR
