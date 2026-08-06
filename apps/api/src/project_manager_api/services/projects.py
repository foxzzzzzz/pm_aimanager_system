from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from project_manager_api.api.schemas import IssueCreate, IssueUpdate, ProgressProposalCreate
from project_manager_api.db.models import (
    AuditLog,
    BindingStatus,
    ChangeProposal,
    ImportRecord,
    ImportStatus,
    Issue,
    IssueStatus,
    MemberBinding,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectVersion,
    ProposalStatus,
)
from project_manager_api.imports.diff import semantic_diff
from project_manager_api.imports.report import ParseResult
from project_manager_api.services.errors import ConflictError, ForbiddenError, NotFoundError


class ProjectService:
    def __init__(self, session: Session, actor_id: str) -> None:
        self.session = session
        self.actor_id = actor_id

    def create_project(self, code: str, name: str) -> dict[str, Any]:
        existing = self.session.scalar(select(Project).where(Project.code == code))
        if existing is not None:
            raise ConflictError("project code already exists")
        project = Project(code=code, name=name)
        self.session.add(project)
        self.session.flush()
        self.session.add(
            ProjectMembership(
                project_id=project.id,
                actor_id=self.actor_id,
                role=ProjectRole.MANAGER,
            )
        )
        self._audit(
            project.id,
            "project.created",
            "project",
            str(project.id),
            after={"code": code, "name": name},
        )
        return _project_dict(project)

    def list_projects(self) -> list[dict[str, Any]]:
        query = (
            select(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .where(ProjectMembership.actor_id == self.actor_id)
            .order_by(Project.created_at.desc())
        )
        return [_project_dict(project) for project in self.session.scalars(query)]

    def create_import(
        self,
        project_id: uuid.UUID,
        filename: str,
        object_key: str,
        result: ParseResult,
    ) -> dict[str, Any]:
        project = self._require_project(project_id, manager=True)
        if result.draft.project.code.strip().casefold() != project.code.strip().casefold():
            raise ConflictError("workbook project code does not match the target project")
        current = self._current_version(project)
        current_snapshot: dict[str, Any] = current.snapshot if current is not None else {}
        draft = result.draft.model_dump(mode="json")
        changes = [
            entry.model_dump(mode="json") for entry in semantic_diff(current_snapshot, draft)
        ]
        record = ImportRecord(
            project_id=project.id,
            filename=filename,
            source_sha256=result.draft.source_sha256,
            object_key=object_key,
            status=ImportStatus.VALIDATED,
            base_version_number=project.current_version_number or 0,
            template_id=result.draft.template_id,
            template_version=result.draft.template_version,
            draft=draft,
            report=result.report.model_dump(mode="json"),
            diff=changes,
        )
        self.session.add(record)
        self.session.flush()
        self._audit(
            project.id,
            "import.validated",
            "import",
            str(record.id),
            after={"filename": filename, "diff_count": len(changes)},
        )
        return _import_dict(record)

    def get_import(self, import_id: uuid.UUID) -> dict[str, Any]:
        record = self.session.get(ImportRecord, import_id)
        if record is None or record.project_id is None:
            raise NotFoundError("import not found")
        self._require_project(record.project_id)
        return _import_dict(record)

    def list_imports(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id)
        query = (
            select(ImportRecord)
            .where(ImportRecord.project_id == project_id)
            .order_by(ImportRecord.created_at.desc())
        )
        return [_import_dict(record) for record in self.session.scalars(query)]

    def cancel_import(self, import_id: uuid.UUID) -> dict[str, Any]:
        record = self._require_import(import_id)
        assert record.project_id is not None
        self._require_project(record.project_id, manager=True)
        if record.status != ImportStatus.VALIDATED:
            raise ConflictError("only validated imports can be cancelled")
        record.status = ImportStatus.CANCELLED
        self._audit(
            record.project_id,
            "import.cancelled",
            "import",
            str(record.id),
        )
        return _import_dict(record)

    def publish_import(self, import_id: uuid.UUID, expected_project_version: int) -> dict[str, Any]:
        record = self._require_import(import_id)
        assert record.project_id is not None
        project = self._require_project(record.project_id, manager=True)
        if record.status not in (ImportStatus.VALIDATED, ImportStatus.CONFLICT):
            raise ConflictError("import is not publishable")
        existing = self.session.scalar(
            select(ProjectVersion).where(
                ProjectVersion.project_id == project.id,
                ProjectVersion.content_sha256 == record.source_sha256,
            )
        )
        if existing is not None:
            record.status = ImportStatus.PUBLISHED
            return _version_dict(existing)

        current_number = project.current_version_number or 0
        if current_number != expected_project_version:
            conflict_paths = self._import_conflict_paths(record, project)
            record.status = ImportStatus.CONFLICT
            raise ConflictError(
                {
                    "message": "project version changed after import validation",
                    "current_version_number": current_number,
                    "conflict_paths": conflict_paths,
                }
            )
        if record.draft is None:
            raise ConflictError("validated import has no draft")
        version = ProjectVersion(
            project_id=project.id,
            version_number=current_number + 1,
            template_id=record.template_id or "unknown",
            template_version=record.template_version or "unknown",
            document_version=str(record.draft["document_version"]),
            content_sha256=record.source_sha256,
            snapshot=record.draft,
        )
        self.session.add(version)
        self.session.flush()
        project.current_version_number = version.version_number
        record.status = ImportStatus.PUBLISHED
        self._audit(
            project.id,
            "import.published",
            "project_version",
            str(version.id),
            before={"version_number": current_number},
            after={"version_number": version.version_number},
        )
        return _version_dict(version)

    def list_versions(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id)
        query = (
            select(ProjectVersion)
            .where(ProjectVersion.project_id == project_id)
            .order_by(ProjectVersion.version_number)
        )
        return [_version_dict(version) for version in self.session.scalars(query)]

    def dashboard(self, project_id: uuid.UUID) -> dict[str, Any]:
        project = self._require_project(project_id)
        version = self._current_version(project)
        snapshot = version.snapshot if version is not None else {}
        open_issue_count = self.session.scalar(
            select(func.count(Issue.id)).where(
                Issue.project_id == project.id,
                Issue.status.not_in((IssueStatus.RESOLVED, IssueStatus.CLOSED)),
            )
        )
        active_plan_name = snapshot.get("active_plan_name")
        active_plan = next(
            (
                plan
                for plan in snapshot.get("plan_versions", [])
                if plan.get("name") == active_plan_name
            ),
            None,
        )
        return {
            "project": _project_dict(project),
            "current_version_number": project.current_version_number or 0,
            "active_plan_name": active_plan_name,
            "milestones": active_plan.get("milestones", {}) if active_plan else {},
            "counts": {
                "members": len(snapshot.get("members", [])),
                "milestones": len(snapshot.get("milestones", [])),
                "product_specs": len(snapshot.get("product_specs", [])),
                "issues_open": open_issue_count or 0,
            },
        }

    def create_progress_proposal(
        self,
        project_id: uuid.UUID,
        milestone_code: str,
        payload: ProgressProposalCreate,
    ) -> dict[str, Any]:
        project = self._require_project(project_id, manager=True)
        if project.current_version_number != payload.base_version_number:
            raise ConflictError("proposal base version is stale")
        version = self._current_version(project)
        if version is None:
            raise ConflictError("project has no published version")
        target_path, before_value = _find_milestone_window(version.snapshot, milestone_code)
        after_value = {
            "state": "scheduled",
            "start_date": payload.start_date.isoformat(),
            "end_date": payload.end_date.isoformat(),
        }
        proposal = ChangeProposal(
            project_id=project.id,
            milestone_code=milestone_code,
            proposal_kind="schedule",
            target_path=target_path,
            base_version_number=payload.base_version_number,
            before_value=before_value,
            after_value=after_value,
            reason=payload.reason,
            status=ProposalStatus.PENDING,
            submitted_by_actor_id=self.actor_id,
        )
        self.session.add(proposal)
        self.session.flush()
        self._audit(
            project.id,
            "change_proposal.created",
            "change_proposal",
            str(proposal.id),
            before=before_value,
            after=after_value,
            reason=payload.reason,
        )
        return _proposal_dict(proposal)

    def approve_proposal(
        self, proposal_id: uuid.UUID, expected_project_version: int
    ) -> dict[str, Any]:
        proposal = self.session.get(ChangeProposal, proposal_id)
        if proposal is None:
            raise NotFoundError("change proposal not found")
        project = self._require_project(proposal.project_id)
        self._require_approval_permission(project, proposal.milestone_code)
        if proposal.status != ProposalStatus.PENDING:
            raise ConflictError("change proposal is already resolved")
        if project.current_version_number != expected_project_version:
            raise ConflictError("project version changed before proposal approval")
        current = self._current_version(project)
        if current is None:
            raise ConflictError("project has no published version")
        snapshot = copy.deepcopy(current.snapshot)
        if proposal.proposal_kind == "completed":
            _replace_milestone_completion(snapshot, proposal.milestone_code, proposal.after_value)
        else:
            _replace_milestone_window(snapshot, proposal.milestone_code, proposal.after_value)
        encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        version = ProjectVersion(
            project_id=project.id,
            version_number=expected_project_version + 1,
            template_id=current.template_id,
            template_version=current.template_version,
            document_version=current.document_version,
            content_sha256=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
            snapshot=snapshot,
        )
        self.session.add(version)
        self.session.flush()
        project.current_version_number = version.version_number
        proposal.status = ProposalStatus.APPROVED
        proposal.approved_by_actor_id = self.actor_id
        proposal.resolved_at = datetime.now(UTC)
        self._audit(
            project.id,
            "change_proposal.approved",
            "change_proposal",
            str(proposal.id),
            before=proposal.before_value,
            after=proposal.after_value,
            reason=proposal.reason,
        )
        return _version_dict(version)

    def list_proposals(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id)
        query = (
            select(ChangeProposal)
            .where(ChangeProposal.project_id == project_id)
            .order_by(ChangeProposal.created_at.desc())
        )
        return [_proposal_dict(proposal) for proposal in self.session.scalars(query)]

    def reject_proposal(self, proposal_id: uuid.UUID, reason: str) -> dict[str, Any]:
        proposal = self.session.get(ChangeProposal, proposal_id)
        if proposal is None:
            raise NotFoundError("change proposal not found")
        project = self._require_project(proposal.project_id)
        self._require_approval_permission(project, proposal.milestone_code)
        if proposal.status != ProposalStatus.PENDING:
            raise ConflictError("change proposal is already resolved")
        proposal.status = ProposalStatus.REJECTED
        proposal.approved_by_actor_id = self.actor_id
        proposal.resolved_at = datetime.now(UTC)
        self._audit(
            project.id,
            "change_proposal.rejected",
            "change_proposal",
            str(proposal.id),
            before=proposal.before_value,
            after=proposal.after_value,
            reason=reason,
        )
        return _proposal_dict(proposal)

    def create_issue(self, project_id: uuid.UUID, payload: IssueCreate) -> dict[str, Any]:
        project = self._require_project(project_id)
        issue = Issue(
            project_id=project.id,
            description=payload.description,
            impact=payload.impact,
            owner_name=payload.owner_name,
            severity=payload.severity,
            due_date=payload.due_date,
            status=IssueStatus.OPEN,
            created_by_actor_id=self.actor_id,
        )
        self.session.add(issue)
        self.session.flush()
        self._audit(
            project.id,
            "issue.created",
            "issue",
            str(issue.id),
            after=_issue_dict(issue),
        )
        return _issue_dict(issue)

    def update_issue(self, issue_id: uuid.UUID, payload: IssueUpdate) -> dict[str, Any]:
        issue = self.session.get(Issue, issue_id)
        if issue is None:
            raise NotFoundError("issue not found")
        self._require_project(issue.project_id, manager=True)
        if issue.revision != payload.expected_revision:
            raise ConflictError("issue revision is stale")
        before = _issue_dict(issue)
        changes = payload.model_dump(exclude={"expected_revision"}, exclude_none=True)
        for field, value in changes.items():
            setattr(issue, field, value)
        issue.revision += 1
        issue.updated_at = datetime.now(UTC)
        self.session.flush()
        after = _issue_dict(issue)
        self._audit(
            issue.project_id,
            "issue.updated",
            "issue",
            str(issue.id),
            before=before,
            after=after,
        )
        return after

    def list_issues(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id)
        query = (
            select(Issue).where(Issue.project_id == project_id).order_by(Issue.created_at.desc())
        )
        return [_issue_dict(issue) for issue in self.session.scalars(query)]

    def list_audit_logs(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id)
        query = (
            select(AuditLog).where(AuditLog.project_id == project_id).order_by(AuditLog.created_at)
        )
        return [_audit_dict(log) for log in self.session.scalars(query)]

    def _require_project(self, project_id: uuid.UUID, manager: bool = False) -> Project:
        project = self.session.get(Project, project_id)
        if project is None:
            raise NotFoundError("project not found")
        membership = self.session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project_id,
                ProjectMembership.actor_id == self.actor_id,
            )
        )
        if membership is None:
            raise ForbiddenError("actor is not a project member")
        if manager and membership.role != ProjectRole.MANAGER:
            raise ForbiddenError("project-manager role is required")
        return project

    def _require_import(self, import_id: uuid.UUID) -> ImportRecord:
        record = self.session.get(ImportRecord, import_id)
        if record is None or record.project_id is None:
            raise NotFoundError("import not found")
        return record

    def _require_approval_permission(self, project: Project, milestone_code: str) -> None:
        membership = self.session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project.id,
                ProjectMembership.actor_id == self.actor_id,
            )
        )
        if membership is not None and membership.role == ProjectRole.MANAGER:
            return
        binding = self.session.scalar(
            select(MemberBinding).where(
                MemberBinding.project_id == project.id,
                MemberBinding.actor_id == self.actor_id,
                MemberBinding.status == BindingStatus.BOUND,
            )
        )
        current = self._current_version(project)
        if binding is not None and current is not None:
            milestone = next(
                (
                    item
                    for item in current.snapshot.get("milestones", [])
                    if item.get("code") == milestone_code
                ),
                None,
            )
            if milestone and binding.member_name in milestone.get("assignments", {}).get("A", []):
                return
        raise ForbiddenError("project manager or accountable member approval is required")

    def _current_version(self, project: Project) -> ProjectVersion | None:
        if project.current_version_number is None:
            return None
        return self.session.scalar(
            select(ProjectVersion).where(
                ProjectVersion.project_id == project.id,
                ProjectVersion.version_number == project.current_version_number,
            )
        )

    def _import_conflict_paths(self, record: ImportRecord, project: Project) -> list[str]:
        proposed_paths = {item["path"] for item in record.diff or []}
        base_snapshot: dict[str, Any] = {}
        if record.base_version_number:
            base = self.session.scalar(
                select(ProjectVersion).where(
                    ProjectVersion.project_id == project.id,
                    ProjectVersion.version_number == record.base_version_number,
                )
            )
            if base is not None:
                base_snapshot = base.snapshot
        current = self._current_version(project)
        current_paths = {
            item.path for item in semantic_diff(base_snapshot, current.snapshot if current else {})
        }
        conflicts = sorted(proposed_paths & current_paths)
        return conflicts or ["project.current_version_number"]

    def _audit(
        self,
        project_id: uuid.UUID,
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                project_id=project_id,
                actor_id=self.actor_id,
                source="admin_web",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before_value=before,
                after_value=after,
                reason=reason,
            )
        )


def _project_dict(project: Project) -> dict[str, Any]:
    return {
        "id": str(project.id),
        "code": project.code,
        "name": project.name,
        "status": project.status,
        "current_version_number": project.current_version_number or 0,
        "created_at": project.created_at.isoformat(),
    }


def _import_dict(record: ImportRecord) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "project_id": str(record.project_id),
        "filename": record.filename,
        "status": record.status,
        "base_version_number": record.base_version_number,
        "template_id": record.template_id,
        "template_version": record.template_version,
        "report": record.report,
        "diff": record.diff or [],
        "diff_count": len(record.diff or []),
        "created_at": record.created_at.isoformat(),
    }


def _version_dict(version: ProjectVersion) -> dict[str, Any]:
    return {
        "id": str(version.id),
        "project_id": str(version.project_id),
        "version_number": version.version_number,
        "template_id": version.template_id,
        "template_version": version.template_version,
        "document_version": version.document_version,
        "content_sha256": version.content_sha256,
        "created_at": version.created_at.isoformat(),
    }


def _proposal_dict(proposal: ChangeProposal) -> dict[str, Any]:
    return {
        "id": str(proposal.id),
        "project_id": str(proposal.project_id),
        "milestone_code": proposal.milestone_code,
        "kind": proposal.proposal_kind,
        "target_path": proposal.target_path,
        "base_version_number": proposal.base_version_number,
        "before_value": proposal.before_value,
        "after_value": proposal.after_value,
        "reason": proposal.reason,
        "status": proposal.status,
    }


def _issue_dict(issue: Issue) -> dict[str, Any]:
    return {
        "id": str(issue.id),
        "project_id": str(issue.project_id),
        "description": issue.description,
        "impact": issue.impact,
        "owner_name": issue.owner_name,
        "severity": issue.severity,
        "due_date": issue.due_date.isoformat(),
        "status": issue.status,
        "revision": issue.revision,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
    }


def _audit_dict(log: AuditLog) -> dict[str, Any]:
    return {
        "id": str(log.id),
        "project_id": str(log.project_id) if log.project_id else None,
        "actor_id": log.actor_id,
        "source": log.source,
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "before_value": log.before_value,
        "after_value": log.after_value,
        "reason": log.reason,
        "created_at": log.created_at.isoformat(),
    }


def _find_milestone_window(
    snapshot: dict[str, Any], milestone_code: str
) -> tuple[str, dict[str, Any]]:
    milestone = next(
        (item for item in snapshot.get("milestones", []) if item.get("code") == milestone_code),
        None,
    )
    if milestone is None:
        raise NotFoundError("milestone not found")
    active_name = snapshot.get("active_plan_name")
    for index, plan in enumerate(snapshot.get("plan_versions", [])):
        if plan.get("name") == active_name:
            window = plan.get("milestones", {}).get(milestone["name"])
            if window is None:
                raise NotFoundError("milestone schedule not found")
            path = f"plan_versions[{index}].milestones.{milestone['name']}"
            return path, dict(window)
    raise NotFoundError("active plan not found")


def _replace_milestone_window(
    snapshot: dict[str, Any], milestone_code: str, after_value: dict[str, Any]
) -> None:
    path, _ = _find_milestone_window(snapshot, milestone_code)
    prefix, milestone_name = path.rsplit(".", maxsplit=1)
    index = int(prefix.split("[")[1].split("]")[0])
    snapshot["plan_versions"][index]["milestones"][milestone_name] = after_value


def _replace_milestone_completion(
    snapshot: dict[str, Any], milestone_code: str, after_value: dict[str, Any]
) -> None:
    milestone = next(
        (item for item in snapshot.get("milestones", []) if item.get("code") == milestone_code),
        None,
    )
    if milestone is None:
        raise NotFoundError("milestone not found")
    milestone["actual_completion"] = after_value
