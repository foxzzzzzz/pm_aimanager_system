from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from project_manager_api.api.schemas import (
    IssueCreate,
    IssueDelete,
    IssueUpdate,
    ProgressProposalCreate,
    ProjectChangeSetCreate,
    ProjectDataOperation,
)
from project_manager_api.db.models import (
    AuditLog,
    BindingStatus,
    ChangeProposal,
    ChangeSetStatus,
    ImportRecord,
    ImportStatus,
    InAppMessage,
    Issue,
    IssueCreateProposal,
    IssueDeleteProposal,
    IssueStatus,
    MemberBinding,
    MobileUser,
    Project,
    ProjectChangeSet,
    ProjectMembership,
    ProjectRole,
    ProjectVersion,
    ProposalStatus,
)
from project_manager_api.domain.models import (
    CanonicalProjectDraft,
    MilestoneDefinition,
    PlanVersionDraft,
    ProductSpecItem,
    ProjectMemberDraft,
)
from project_manager_api.imports.diff import semantic_diff
from project_manager_api.imports.report import ParseResult
from project_manager_api.services.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PersistedConflictError,
)
from project_manager_api.services.member_roles import member_role


class ProjectService:
    def __init__(
        self,
        session: Session,
        actor_id: str,
        business_date: date | None = None,
        upcoming_days: int = 14,
    ) -> None:
        self.session = session
        self.actor_id = actor_id
        self.business_date = business_date or date.today()
        self.upcoming_days = upcoming_days

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

    def update_empty_project(
        self, project_id: uuid.UUID, code: str, name: str
    ) -> dict[str, Any]:
        project = self._require_project(project_id, manager=True, lock=True)
        if project.current_version_number is not None:
            raise ConflictError("published projects cannot be edited")
        existing = self.session.scalar(
            select(Project).where(Project.code == code, Project.id != project_id)
        )
        if existing is not None:
            raise ConflictError("project code already exists")
        before = {"code": project.code, "name": project.name}
        project.code = code
        project.name = name
        self._audit(
            project.id,
            "project.updated",
            "project",
            str(project.id),
            before=before,
            after={"code": code, "name": name},
        )
        return _project_dict(project)

    def delete_empty_project(self, project_id: uuid.UUID) -> dict[str, Any]:
        project = self._require_project(project_id, manager=True, lock=True)
        if project.current_version_number is not None:
            raise ConflictError("published projects cannot be deleted")
        self.session.delete(project)
        return {}

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
        if result.draft.project.name.strip().casefold() != project.name.strip().casefold():
            raise ConflictError("workbook project name does not match the target project")
        current = self._current_version(project)
        current_snapshot: dict[str, Any] = current.snapshot if current is not None else {}
        draft = result.draft.model_dump(mode="json")
        changes = [
            entry.model_dump(mode="json")
            for entry in _business_diff(current_snapshot, draft)
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

    def create_project_from_import(
        self, filename: str, object_key: str, result: ParseResult
    ) -> dict[str, Any]:
        existing = self.session.scalar(
            select(Project).where(Project.code == result.draft.project.code)
        )
        if existing is not None:
            raise ConflictError(
                "project code already exists; select the existing project to import"
            )
        project = self.create_project(result.draft.project.code, result.draft.project.name)
        imported = self.create_import(uuid.UUID(project["id"]), filename, object_key, result)
        return {"project": project, "import": imported}

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
        project = self._require_project(record.project_id, manager=True, lock=True)
        if record.status not in (ImportStatus.VALIDATED, ImportStatus.CONFLICT):
            raise ConflictError("import is not publishable")
        if record.draft is None:
            raise ConflictError("validated import has no draft")
        draft_hash = _business_hash(record.draft)
        current = self._current_version(project)
        if current is not None and current.content_sha256 == draft_hash:
            record.status = ImportStatus.PUBLISHED
            return _version_dict(current)
        existing = self.session.scalar(
            select(ProjectVersion).where(
                ProjectVersion.project_id == project.id,
                ProjectVersion.content_sha256 == draft_hash,
                ProjectVersion.version_number != (project.current_version_number or 0),
            )
        )
        if existing is not None:
            record.status = ImportStatus.CONFLICT
            raise PersistedConflictError(
                "workbook matches a historical version; current version was not changed"
            )

        current_number = project.current_version_number or 0
        if current_number != expected_project_version:
            conflict_paths = self._import_conflict_paths(record, project)
            record.status = ImportStatus.CONFLICT
            raise PersistedConflictError(
                {
                    "message": "project version changed after import validation",
                    "current_version_number": current_number,
                    "conflict_paths": conflict_paths,
                }
            )
        version = ProjectVersion(
            project_id=project.id,
            version_number=current_number + 1,
            template_id=record.template_id or "unknown",
            template_version=record.template_version or "unknown",
            document_version=str(record.draft["document_version"]),
            content_sha256=draft_hash,
            snapshot=record.draft,
        )
        self.session.add(version)
        self.session.flush()
        project.current_version_number = version.version_number
        record.status = ImportStatus.PUBLISHED
        self._reconcile_member_bindings(project, record.draft)
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
        active_milestones = active_plan.get("milestones", {}) if active_plan else {}
        tasks = [
            {
                **milestone,
                "plan": active_milestones.get(milestone.get("name")),
                "risk": milestone_risk(
                    {
                        **milestone,
                        "plan": active_milestones.get(milestone.get("name")),
                    },
                    self.business_date,
                    self.upcoming_days,
                ),
            }
            for milestone in snapshot.get("milestones", [])
            if active_milestones.get(milestone.get("name"), {}).get("state")
            != "not_applicable"
        ]
        issues = list(
            self.session.scalars(
                select(Issue)
                .where(Issue.project_id == project.id)
                .order_by(Issue.created_at.desc())
            )
        )
        return {
            "project": _project_dict(project),
            "current_version_number": project.current_version_number or 0,
            "business_date": self.business_date.isoformat(),
            "active_plan_name": active_plan_name,
            "milestones": active_milestones,
            "tasks": tasks,
            "issues": [self._issue_dict(issue) for issue in issues],
            "counts": {
                "members": len(snapshot.get("members", [])),
                "milestones": len(snapshot.get("milestones", [])),
                "product_specs": len(snapshot.get("product_specs", [])),
                "issues_open": open_issue_count or 0,
            },
        }

    def review(self, project_id: uuid.UUID) -> dict[str, Any]:
        project = self._require_project(project_id)
        version = self._current_version(project)
        snapshot = version.snapshot if version is not None else {}
        active_plan_name = snapshot.get("active_plan_name")
        active_plan = next(
            (
                plan
                for plan in snapshot.get("plan_versions", [])
                if plan.get("name") == active_plan_name
            ),
            None,
        )
        active_milestones = active_plan.get("milestones", {}) if active_plan else {}
        milestones = [
            {
                "code": milestone.get("code"),
                "name": milestone.get("name"),
                "output": milestone.get("output"),
                "schedule": active_milestones.get(
                    milestone.get("name"),
                    {"state": "tbd", "start_date": None, "end_date": None},
                ),
                "assignments": milestone.get("assignments", {}),
                "risk_note": milestone.get("risk_note"),
            }
            for milestone in snapshot.get("milestones", [])
        ]
        return {
            "current_version_number": project.current_version_number or 0,
            "document_version": snapshot.get("document_version"),
            "active_plan_name": active_plan_name,
            "tbd_count": sum(
                milestone["schedule"].get("state") == "tbd" for milestone in milestones
            ),
            "product_specs": snapshot.get("product_specs", []),
            "members": [
                {
                    "name": member.get("name"),
                    "role": member.get("role"),
                    "notes": member.get("notes"),
                }
                for member in snapshot.get("members", [])
            ],
            "milestones": milestones,
        }

    def editable_data(self, project_id: uuid.UUID) -> dict[str, Any]:
        project = self._require_project(project_id, manager=True)
        version = self._current_version(project)
        if version is None:
            raise ConflictError("project has no published version")
        return {
            "current_version_number": project.current_version_number,
            **copy.deepcopy(version.snapshot),
        }

    def create_change_set(
        self, project_id: uuid.UUID, payload: ProjectChangeSetCreate
    ) -> dict[str, Any]:
        project = self._require_project(project_id, manager=True)
        if project.current_version_number != payload.base_version_number:
            raise ConflictError("change set base version is stale")
        current = self._current_version(project)
        if current is None:
            raise ConflictError("project has no published version")
        operations = [item.model_dump(mode="json") for item in payload.operations]
        draft = copy.deepcopy(current.snapshot)
        _apply_project_data_operations(draft, payload.operations)
        _validate_editable_snapshot(draft, current.snapshot)
        changes = [item.model_dump(mode="json") for item in _business_diff(current.snapshot, draft)]
        if not changes:
            raise ConflictError("change set does not contain business changes")
        change_set = ProjectChangeSet(
            project_id=project.id,
            base_version_number=payload.base_version_number,
            source="admin_web",
            operations=operations,
            diff=changes,
            reason=payload.reason,
            status=ChangeSetStatus.PENDING,
            submitted_by_actor_id=self.actor_id,
        )
        self.session.add(change_set)
        self.session.flush()
        self._audit(
            project.id,
            "project_change_set.created",
            "project_change_set",
            str(change_set.id),
            after={"operations": operations, "diff": changes},
            reason=payload.reason,
        )
        return _change_set_dict(change_set)

    def list_change_sets(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id, manager=True)
        query = (
            select(ProjectChangeSet)
            .where(ProjectChangeSet.project_id == project_id)
            .order_by(ProjectChangeSet.created_at.desc())
        )
        return [_change_set_dict(item) for item in self.session.scalars(query)]

    def get_change_set(self, change_set_id: uuid.UUID) -> dict[str, Any]:
        change_set = self._require_change_set(change_set_id)
        self._require_project(change_set.project_id, manager=True)
        return _change_set_dict(change_set)

    def publish_change_set(
        self, change_set_id: uuid.UUID, expected_project_version: int
    ) -> dict[str, Any]:
        change_set = self._require_change_set(change_set_id)
        project = self._require_project(change_set.project_id, manager=True, lock=True)
        if change_set.status != ChangeSetStatus.PENDING:
            raise ConflictError("change set is already resolved")
        if (
            project.current_version_number != expected_project_version
            or change_set.base_version_number != expected_project_version
        ):
            raise ConflictError("change set base version is stale")
        current = self._current_version(project)
        if current is None:
            raise ConflictError("project has no published version")
        snapshot = copy.deepcopy(current.snapshot)
        operations = [ProjectDataOperation.model_validate(item) for item in change_set.operations]
        _apply_project_data_operations(snapshot, operations)
        _validate_editable_snapshot(snapshot, current.snapshot)
        version = ProjectVersion(
            project_id=project.id,
            version_number=expected_project_version + 1,
            template_id=current.template_id,
            template_version=current.template_version,
            document_version=current.document_version,
            content_sha256=_business_hash(snapshot),
            snapshot=snapshot,
        )
        self.session.add(version)
        self.session.flush()
        project.current_version_number = version.version_number
        change_set.status = ChangeSetStatus.PUBLISHED
        change_set.published_by_actor_id = self.actor_id
        change_set.resolved_at = datetime.now(UTC)
        self._reconcile_member_bindings(project, snapshot)
        self._audit(
            project.id,
            "project_change_set.published",
            "project_change_set",
            str(change_set.id),
            before={"version_number": expected_project_version},
            after={"version_number": version.version_number, "diff": change_set.diff},
            reason=change_set.reason,
        )
        return _version_dict(version)

    def cancel_change_set(self, change_set_id: uuid.UUID) -> dict[str, Any]:
        change_set = self._require_change_set(change_set_id)
        project = self._require_project(change_set.project_id, manager=True)
        if change_set.status != ChangeSetStatus.PENDING:
            raise ConflictError("change set is already resolved")
        change_set.status = ChangeSetStatus.CANCELLED
        change_set.resolved_at = datetime.now(UTC)
        self._audit(
            project.id,
            "project_change_set.cancelled",
            "project_change_set",
            str(change_set.id),
            reason=change_set.reason,
        )
        return _change_set_dict(change_set)

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
        project = self._require_project(proposal.project_id, lock=True)
        self.session.refresh(proposal)
        self._require_approval_permission(project, proposal)
        if proposal.status != ProposalStatus.PENDING:
            raise ConflictError("change proposal is already resolved")
        if project.current_version_number != expected_project_version:
            raise ConflictError("project version changed before proposal approval")
        if proposal.base_version_number != expected_project_version:
            raise ConflictError("proposal base version is stale")
        current = self._current_version(project)
        if current is None:
            raise ConflictError("project has no published version")
        snapshot = copy.deepcopy(current.snapshot)
        if proposal.proposal_kind == "completed":
            current_value = _find_milestone_completion(snapshot, proposal.milestone_code)
            if current_value != proposal.before_value:
                raise ConflictError("proposal target changed after submission")
            _replace_milestone_completion(snapshot, proposal.milestone_code, proposal.after_value)
        else:
            _, current_value = _find_milestone_window(snapshot, proposal.milestone_code)
            if current_value != proposal.before_value:
                raise ConflictError("proposal target changed after submission")
            _replace_milestone_window(snapshot, proposal.milestone_code, proposal.after_value)
        version = ProjectVersion(
            project_id=project.id,
            version_number=expected_project_version + 1,
            template_id=current.template_id,
            template_version=current.template_version,
            document_version=current.document_version,
            content_sha256=_business_hash(snapshot),
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
        project = self._require_project(proposal.project_id, lock=True)
        self.session.refresh(proposal)
        self._require_approval_permission(project, proposal)
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
        self._validate_issue_raci(project, payload)
        issue = Issue(
            project_id=project.id,
            description=payload.description,
            impact=payload.impact,
            owner_name=payload.owner_name,
            accountable_names=payload.accountable_names,
            consulted_names=payload.consulted_names,
            informed_names=payload.informed_names,
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
            after=self._issue_dict(issue),
        )
        return self._issue_dict(issue)

    def create_issue_proposal(
        self, project_id: uuid.UUID, payload: IssueCreate
    ) -> dict[str, Any]:
        project = self._require_project(project_id)
        self._validate_issue_raci(project, payload)
        proposal = IssueCreateProposal(
            project_id=project.id,
            payload=payload.model_dump(mode="json"),
            submitted_by_actor_id=self.actor_id,
        )
        self.session.add(proposal)
        self.session.flush()
        self._audit(
            project.id,
            "issue_create_proposal.created",
            "issue_create_proposal",
            str(proposal.id),
            after=_issue_create_proposal_dict(proposal),
        )
        return _issue_create_proposal_dict(proposal)

    def list_issue_create_proposals(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id, manager=True)
        query = (
            select(IssueCreateProposal)
            .where(IssueCreateProposal.project_id == project_id)
            .order_by(IssueCreateProposal.created_at.desc())
        )
        return [_issue_create_proposal_dict(item) for item in self.session.scalars(query)]

    def approve_issue_create_proposal(
        self, proposal_id: uuid.UUID
    ) -> dict[str, Any]:
        proposal = self.session.scalar(
            select(IssueCreateProposal)
            .where(IssueCreateProposal.id == proposal_id)
            .with_for_update()
        )
        if proposal is None:
            raise NotFoundError("issue create proposal not found")
        self._require_project(proposal.project_id, manager=True)
        if proposal.status != ProposalStatus.PENDING:
            raise ConflictError("issue create proposal is already resolved")
        issue = self.create_issue(proposal.project_id, IssueCreate.model_validate(proposal.payload))
        proposal.status = ProposalStatus.APPROVED
        proposal.resolved_by_actor_id = self.actor_id
        proposal.issue_id = uuid.UUID(issue["id"])
        proposal.resolved_at = datetime.now(UTC)
        result = _issue_create_proposal_dict(proposal)
        self._audit(
            proposal.project_id,
            "issue_create_proposal.approved",
            "issue_create_proposal",
            str(proposal.id),
            before={"status": ProposalStatus.PENDING},
            after=result,
        )
        self._notify_mobile_actor(
            proposal.submitted_by_actor_id,
            proposal.project_id,
            "issue_create_approved",
            "重点问题新增申请已批准",
            f"问题“{proposal.payload['description']}”已进入正式问题列表。",
        )
        return result

    def reject_issue_create_proposal(
        self, proposal_id: uuid.UUID, reason: str
    ) -> dict[str, Any]:
        proposal = self.session.scalar(
            select(IssueCreateProposal)
            .where(IssueCreateProposal.id == proposal_id)
            .with_for_update()
        )
        if proposal is None:
            raise NotFoundError("issue create proposal not found")
        self._require_project(proposal.project_id, manager=True)
        if proposal.status != ProposalStatus.PENDING:
            raise ConflictError("issue create proposal is already resolved")
        proposal.status = ProposalStatus.REJECTED
        proposal.resolved_by_actor_id = self.actor_id
        proposal.resolution_reason = reason
        proposal.resolved_at = datetime.now(UTC)
        result = _issue_create_proposal_dict(proposal)
        self._audit(
            proposal.project_id,
            "issue_create_proposal.rejected",
            "issue_create_proposal",
            str(proposal.id),
            before={"status": ProposalStatus.PENDING},
            after=result,
            reason=reason,
        )
        self._notify_mobile_actor(
            proposal.submitted_by_actor_id,
            proposal.project_id,
            "issue_create_rejected",
            "重点问题新增申请已驳回",
            f"问题“{proposal.payload['description']}”未通过审批：{reason}",
        )
        return result

    def update_issue(self, issue_id: uuid.UUID, payload: IssueUpdate) -> dict[str, Any]:
        issue = self.session.get(Issue, issue_id)
        if issue is None:
            raise NotFoundError("issue not found")
        self._require_project(issue.project_id, manager=True)
        return self.update_issue_as_member(issue, payload)

    def create_issue_delete_proposal(
        self, issue_id: uuid.UUID, payload: IssueDelete
    ) -> dict[str, Any]:
        issue = self.session.get(Issue, issue_id)
        if issue is None:
            raise NotFoundError("issue not found")
        self._require_project(issue.project_id)
        if issue.status == IssueStatus.CLOSED:
            raise ConflictError("issue is already closed")
        if issue.revision != payload.expected_revision:
            raise ConflictError("issue revision is stale")
        pending = self.session.scalar(
            select(IssueDeleteProposal).where(
                IssueDeleteProposal.issue_id == issue.id,
                IssueDeleteProposal.status == ProposalStatus.PENDING,
            )
        )
        if pending is not None:
            raise ConflictError("issue already has a pending delete proposal")
        proposal = IssueDeleteProposal(
            project_id=issue.project_id,
            issue_id=issue.id,
            expected_revision=payload.expected_revision,
            reason=payload.reason,
            submitted_by_actor_id=self.actor_id,
        )
        self.session.add(proposal)
        self.session.flush()
        result = _issue_delete_proposal_dict(
            proposal, self.business_date, self.upcoming_days
        )
        self._audit(
            issue.project_id,
            "issue_delete_proposal.created",
            "issue_delete_proposal",
            str(proposal.id),
            after=result,
            reason=payload.reason,
        )
        return result

    def list_issue_delete_proposals(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id, manager=True)
        query = (
            select(IssueDeleteProposal)
            .where(IssueDeleteProposal.project_id == project_id)
            .order_by(IssueDeleteProposal.created_at.desc())
        )
        return [
            _issue_delete_proposal_dict(item, self.business_date, self.upcoming_days)
            for item in self.session.scalars(query)
        ]

    def approve_issue_delete_proposal(self, proposal_id: uuid.UUID) -> dict[str, Any]:
        proposal = self.session.scalar(
            select(IssueDeleteProposal)
            .where(IssueDeleteProposal.id == proposal_id)
            .with_for_update()
        )
        if proposal is None:
            raise NotFoundError("issue delete proposal not found")
        self._require_project(proposal.project_id, manager=True)
        if proposal.status != ProposalStatus.PENDING:
            raise ConflictError("issue delete proposal is already resolved")
        issue = self.session.get(Issue, proposal.issue_id)
        if issue is None:
            raise NotFoundError("issue not found")
        self.delete_issue_as_member(
            issue,
            IssueDelete(expected_revision=proposal.expected_revision, reason=proposal.reason),
        )
        proposal.status = ProposalStatus.APPROVED
        proposal.resolved_by_actor_id = self.actor_id
        proposal.resolved_at = datetime.now(UTC)
        result = _issue_delete_proposal_dict(
            proposal, self.business_date, self.upcoming_days
        )
        self._audit(
            proposal.project_id,
            "issue_delete_proposal.approved",
            "issue_delete_proposal",
            str(proposal.id),
            before={"status": ProposalStatus.PENDING},
            after=result,
        )
        self._notify_mobile_actor(
            proposal.submitted_by_actor_id,
            proposal.project_id,
            "issue_delete_approved",
            "重点问题删除申请已批准",
            f"问题“{proposal.issue.description}”已关闭。",
        )
        return result

    def reject_issue_delete_proposal(
        self, proposal_id: uuid.UUID, reason: str
    ) -> dict[str, Any]:
        proposal = self.session.scalar(
            select(IssueDeleteProposal)
            .where(IssueDeleteProposal.id == proposal_id)
            .with_for_update()
        )
        if proposal is None:
            raise NotFoundError("issue delete proposal not found")
        self._require_project(proposal.project_id, manager=True)
        if proposal.status != ProposalStatus.PENDING:
            raise ConflictError("issue delete proposal is already resolved")
        proposal.status = ProposalStatus.REJECTED
        proposal.resolved_by_actor_id = self.actor_id
        proposal.resolution_reason = reason
        proposal.resolved_at = datetime.now(UTC)
        result = _issue_delete_proposal_dict(
            proposal, self.business_date, self.upcoming_days
        )
        self._audit(
            proposal.project_id,
            "issue_delete_proposal.rejected",
            "issue_delete_proposal",
            str(proposal.id),
            before={"status": ProposalStatus.PENDING},
            after=result,
            reason=reason,
        )
        self._notify_mobile_actor(
            proposal.submitted_by_actor_id,
            proposal.project_id,
            "issue_delete_rejected",
            "重点问题删除申请已驳回",
            f"问题“{proposal.issue.description}”继续保留：{reason}",
        )
        return result

    def delete_issue_as_member(
        self, issue: Issue, payload: IssueDelete
    ) -> dict[str, Any]:
        before = self._issue_dict(issue)
        updated_issue = self.session.scalar(
            update(Issue)
            .where(Issue.id == issue.id, Issue.revision == payload.expected_revision)
            .values(
                status=IssueStatus.CLOSED,
                revision=payload.expected_revision + 1,
                updated_at=datetime.now(UTC),
            )
            .returning(Issue)
            .execution_options(populate_existing=True)
        )
        if updated_issue is None:
            raise ConflictError("issue revision is stale")
        after = self._issue_dict(updated_issue)
        self._audit(
            issue.project_id,
            "issue.deleted",
            "issue",
            str(issue.id),
            before=before,
            after=after,
            reason=payload.reason,
        )
        return after

    def update_issue_as_member(self, issue: Issue, payload: IssueUpdate) -> dict[str, Any]:
        project = self._require_project(issue.project_id)
        self._validate_issue_raci(project, payload, issue)
        before = self._issue_dict(issue)
        changes = payload.model_dump(exclude={"expected_revision"}, exclude_none=True)
        updated_issue = self.session.scalar(
            update(Issue)
            .where(Issue.id == issue.id, Issue.revision == payload.expected_revision)
            .values(
                **changes,
                revision=payload.expected_revision + 1,
                updated_at=datetime.now(UTC),
            )
            .returning(Issue)
            .execution_options(populate_existing=True)
        )
        if updated_issue is None:
            raise ConflictError("issue revision is stale")
        after = self._issue_dict(updated_issue)
        self._audit(
            issue.project_id,
            "issue.updated",
            "issue",
            str(issue.id),
            before=before,
            after=after,
        )
        return after

    def _validate_issue_raci(
        self, project: Project, payload: IssueCreate | IssueUpdate, issue: Issue | None = None
    ) -> None:
        version = self._current_version(project)
        member_names = {
            item["name"] for item in (version.snapshot if version else {}).get("members", [])
        }
        owner_name = (
            payload.owner_name
            if payload.owner_name is not None
            else issue.owner_name if issue else ""
        )
        accountable_names = (
            payload.accountable_names
            if payload.accountable_names is not None
            else issue.accountable_names if issue else []
        )
        consulted_names = (
            payload.consulted_names
            if payload.consulted_names is not None
            else issue.consulted_names if issue else []
        )
        informed_names = (
            payload.informed_names
            if payload.informed_names is not None
            else issue.informed_names if issue else []
        )
        role_names = {
            owner_name,
            *accountable_names,
            *consulted_names,
            *informed_names,
        }
        if not accountable_names:
            raise ConflictError("issue accountable member is required")
        unknown = sorted(role_names - member_names)
        if unknown:
            message = f"issue RACI members are not in the current project: {', '.join(unknown)}"
            raise ConflictError(message)

    def _reconcile_member_bindings(
        self, project: Project, snapshot: dict[str, Any]
    ) -> None:
        member_names = {item["name"] for item in snapshot.get("members", [])}
        bindings = self.session.scalars(
            select(MemberBinding).where(
                MemberBinding.project_id == project.id,
                MemberBinding.status != BindingStatus.REVOKED,
            )
        )
        for binding in bindings:
            if binding.member_name not in member_names:
                binding.status = BindingStatus.REVOKED
                if binding.actor_id:
                    self.session.execute(
                        delete(ProjectMembership).where(
                            ProjectMembership.project_id == project.id,
                            ProjectMembership.actor_id == binding.actor_id,
                        )
                    )
                continue
            if binding.actor_id:
                membership = self.session.scalar(
                    select(ProjectMembership).where(
                        ProjectMembership.project_id == project.id,
                        ProjectMembership.actor_id == binding.actor_id,
                    )
                )
                if membership is not None:
                    membership.role = member_role(snapshot, binding.member_name)
                else:
                    self.session.add(
                        ProjectMembership(
                            project_id=project.id,
                            actor_id=binding.actor_id,
                            role=member_role(snapshot, binding.member_name),
                        )
                    )

    def list_issues(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id)
        query = (
            select(Issue).where(Issue.project_id == project_id).order_by(Issue.created_at.desc())
        )
        return [self._issue_dict(issue) for issue in self.session.scalars(query)]

    def _issue_dict(self, issue: Issue) -> dict[str, Any]:
        return _issue_dict(issue, self.business_date, self.upcoming_days)

    def list_audit_logs(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self._require_project(project_id)
        query = (
            select(AuditLog).where(AuditLog.project_id == project_id).order_by(AuditLog.created_at)
        )
        return [_audit_dict(log) for log in self.session.scalars(query)]

    def _require_project(
        self, project_id: uuid.UUID, manager: bool = False, lock: bool = False
    ) -> Project:
        if lock:
            project = self.session.scalar(
                select(Project).where(Project.id == project_id).with_for_update()
            )
        else:
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

    def _notify_mobile_actor(
        self,
        actor_id: str,
        project_id: uuid.UUID,
        message_type: str,
        title: str,
        body: str,
    ) -> None:
        if not actor_id.startswith("mobile:"):
            return
        try:
            user_id = uuid.UUID(actor_id.removeprefix("mobile:"))
        except ValueError:
            return
        if self.session.get(MobileUser, user_id) is None:
            return
        self.session.add(
            InAppMessage(
                user_id=user_id,
                project_id=project_id,
                type=message_type,
                title=title,
                body=body,
            )
        )

    def _require_import(self, import_id: uuid.UUID) -> ImportRecord:
        record = self.session.get(ImportRecord, import_id)
        if record is None or record.project_id is None:
            raise NotFoundError("import not found")
        return record

    def _require_change_set(self, change_set_id: uuid.UUID) -> ProjectChangeSet:
        change_set = self.session.get(ProjectChangeSet, change_set_id)
        if change_set is None:
            raise NotFoundError("change set not found")
        return change_set

    def _require_approval_permission(
        self, project: Project, proposal: ChangeProposal
    ) -> None:
        membership = self.session.scalar(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project.id,
                ProjectMembership.actor_id == self.actor_id,
            )
        )
        if membership is not None and membership.role == ProjectRole.MANAGER:
            return
        if proposal.submitted_by_actor_id == self.actor_id:
            raise ForbiddenError("non-manager submitters cannot resolve their own proposal")
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
                    if item.get("code") == proposal.milestone_code
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
            item.path for item in _business_diff(base_snapshot, current.snapshot if current else {})
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
        "created_at": proposal.created_at.isoformat(),
    }


def _issue_create_proposal_dict(proposal: IssueCreateProposal) -> dict[str, Any]:
    return {
        "id": str(proposal.id),
        "project_id": str(proposal.project_id),
        "payload": proposal.payload,
        "status": proposal.status,
        "submitted_by_actor_id": proposal.submitted_by_actor_id,
        "resolved_by_actor_id": proposal.resolved_by_actor_id,
        "resolution_reason": proposal.resolution_reason,
        "issue_id": str(proposal.issue_id) if proposal.issue_id else None,
        "created_at": proposal.created_at.isoformat(),
        "resolved_at": proposal.resolved_at.isoformat() if proposal.resolved_at else None,
    }


def _issue_delete_proposal_dict(
    proposal: IssueDeleteProposal, business_date: date, upcoming_days: int
) -> dict[str, Any]:
    return {
        "id": str(proposal.id),
        "project_id": str(proposal.project_id),
        "issue_id": str(proposal.issue_id),
        "issue_description": proposal.issue.description,
        "issue": _issue_dict(proposal.issue, business_date, upcoming_days),
        "expected_revision": proposal.expected_revision,
        "reason": proposal.reason,
        "status": proposal.status,
        "submitted_by_actor_id": proposal.submitted_by_actor_id,
        "resolved_by_actor_id": proposal.resolved_by_actor_id,
        "resolution_reason": proposal.resolution_reason,
        "created_at": proposal.created_at.isoformat(),
        "resolved_at": proposal.resolved_at.isoformat() if proposal.resolved_at else None,
    }


def _change_set_dict(change_set: ProjectChangeSet) -> dict[str, Any]:
    return {
        "id": str(change_set.id),
        "project_id": str(change_set.project_id),
        "base_version_number": change_set.base_version_number,
        "source": change_set.source,
        "operations": change_set.operations,
        "diff": change_set.diff,
        "reason": change_set.reason,
        "status": change_set.status,
        "submitted_by_actor_id": change_set.submitted_by_actor_id,
        "published_by_actor_id": change_set.published_by_actor_id,
        "created_at": change_set.created_at.isoformat(),
        "resolved_at": change_set.resolved_at.isoformat() if change_set.resolved_at else None,
    }


def _issue_dict(issue: Issue, business_date: date, upcoming_days: int) -> dict[str, Any]:
    return {
        "id": str(issue.id),
        "project_id": str(issue.project_id),
        "description": issue.description,
        "impact": issue.impact,
        "owner_name": issue.owner_name,
        "accountable_names": issue.accountable_names,
        "consulted_names": issue.consulted_names,
        "informed_names": issue.informed_names,
        "risk": _issue_risk(issue, business_date, upcoming_days),
        "severity": issue.severity,
        "due_date": issue.due_date.isoformat(),
        "status": issue.status,
        "revision": issue.revision,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
    }


def _issue_risk(issue: Issue, business_date: date, upcoming_days: int) -> str:
    today = business_date
    if issue.status in (IssueStatus.RESOLVED, IssueStatus.CLOSED, "resolved", "closed"):
        return "completed"
    if issue.due_date < today:
        return "overdue"
    if issue.due_date <= today + timedelta(days=upcoming_days):
        return "upcoming"
    return "todo"


def milestone_risk(milestone: dict[str, Any], business_date: date, upcoming_days: int) -> str:
    if milestone.get("actual_completion", {}).get("end_date"):
        return "completed"
    plan = milestone.get("plan")
    if not plan or plan.get("state") == "not_applicable":
        return "todo"
    end_date_text = plan.get("end_date")
    if not end_date_text:
        return "todo"
    end_date = date.fromisoformat(end_date_text)
    if end_date < business_date:
        return "overdue"
    if end_date <= business_date + timedelta(days=upcoming_days):
        return "upcoming"
    return "todo"


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


def _find_milestone_completion(
    snapshot: dict[str, Any], milestone_code: str
) -> dict[str, Any] | None:
    milestone = next(
        (item for item in snapshot.get("milestones", []) if item.get("code") == milestone_code),
        None,
    )
    if milestone is None:
        raise NotFoundError("milestone not found")
    value = milestone.get("actual_completion")
    return dict(value) if isinstance(value, dict) else value


def _business_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    business = copy.deepcopy(snapshot)
    business.pop("source_sha256", None)
    return business


def _business_diff(before: dict[str, Any], after: dict[str, Any]) -> list[Any]:
    return semantic_diff(_business_snapshot(before), _business_snapshot(after))


def _business_hash(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(
        _business_snapshot(snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _apply_project_data_operations(
    snapshot: dict[str, Any], operations: list[ProjectDataOperation]
) -> None:
    for operation in operations:
        if operation.value is not None:
            allowed_fields = {
                "product_spec": set(ProductSpecItem.model_fields),
                "member": set(ProjectMemberDraft.model_fields),
                "milestone": set(MilestoneDefinition.model_fields),
                "plan": set(PlanVersionDraft.model_fields),
                "raci": {"R", "A", "C", "I"},
            }[operation.resource]
            unknown_fields = sorted(set(operation.value) - allowed_fields)
            if unknown_fields:
                raise ConflictError(
                    f"{operation.resource} contains unknown fields: {', '.join(unknown_fields)}"
                )
        if operation.resource == "raci":
            milestone = next(
                (
                    item
                    for item in snapshot.get("milestones", [])
                    if str(item.get("code")) == operation.key
                ),
                None,
            )
            if milestone is None:
                raise NotFoundError("milestone not found")
            if operation.op == "remove":
                milestone["assignments"] = {}
            else:
                milestone["assignments"] = copy.deepcopy(operation.value)
            continue

        collection_name, key_field = {
            "product_spec": ("product_specs", "row_number"),
            "member": ("members", "name"),
            "milestone": ("milestones", "code"),
            "plan": ("plan_versions", "name"),
        }[operation.resource]
        collection = snapshot.setdefault(collection_name, [])
        index = next(
            (
                position
                for position, item in enumerate(collection)
                if str(item.get(key_field)) == operation.key
            ),
            None,
        )
        if operation.op == "add":
            if index is not None:
                raise ConflictError(f"{operation.resource} already exists")
            value = copy.deepcopy(operation.value)
            if value is None or str(value.get(key_field)) != operation.key:
                raise ConflictError(f"{operation.resource} key does not match value")
            collection.append(value)
        elif operation.op == "replace":
            if index is None:
                raise NotFoundError(f"{operation.resource} not found")
            value = copy.deepcopy(operation.value)
            if value is None:
                raise ConflictError(f"{operation.resource} replacement is missing")
            collection[index] = value
        else:
            if index is None:
                raise NotFoundError(f"{operation.resource} not found")
            collection.pop(index)


def _validate_editable_snapshot(
    snapshot: dict[str, Any], baseline: dict[str, Any] | None = None
) -> None:
    try:
        CanonicalProjectDraft.model_validate(snapshot)
    except ValueError as exc:
        raise ConflictError(f"invalid project data: {exc}") from exc

    product_rows = [item.get("row_number") for item in snapshot.get("product_specs", [])]
    if len(product_rows) != len(set(product_rows)):
        raise ConflictError("product specification row numbers must be unique")
    members = [str(item.get("name")) for item in snapshot.get("members", [])]
    member_names = set(members)
    if len(members) != len(member_names):
        raise ConflictError("member names must be unique")
    milestones = snapshot.get("milestones", [])
    milestone_codes = [str(item.get("code")) for item in milestones]
    milestone_names = [str(item.get("name")) for item in milestones]
    if len(milestone_codes) != len(set(milestone_codes)):
        raise ConflictError("milestone codes must be unique")
    if len(milestone_names) != len(set(milestone_names)):
        raise ConflictError("milestone names must be unique")
    baseline_member_names = {
        str(item.get("name")) for item in (baseline or {}).get("members", [])
    }
    baseline_unknown = {
        name
        for milestone in (baseline or {}).get("milestones", [])
        for names in milestone.get("assignments", {}).values()
        for name in names
        if name not in baseline_member_names
    }
    for milestone in milestones:
        for names in milestone.get("assignments", {}).values():
            unknown = sorted(set(names) - member_names - baseline_unknown)
            if unknown:
                raise ConflictError(
                    f"RACI references unknown members: {', '.join(unknown)}"
                )
    managers = [
        item.get("name")
        for item in snapshot.get("members", [])
        if item.get("is_project_manager") is True
        or "项目经理"
        in {part.strip() for part in str(item.get("role", "")).split("/")}
    ]
    if len(managers) != 1:
        raise ConflictError("project data must contain exactly one project manager")
    plans = snapshot.get("plan_versions", [])
    plan_names = [str(item.get("name")) for item in plans]
    if len(plan_names) != len(set(plan_names)):
        raise ConflictError("plan names must be unique")
    if snapshot.get("active_plan_name") not in set(plan_names):
        raise ConflictError("active plan does not exist")
    expected_milestones = set(milestone_names)
    for plan in plans:
        if set(plan.get("milestones", {})) != expected_milestones:
            raise ConflictError("plan milestone references are incomplete")


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
