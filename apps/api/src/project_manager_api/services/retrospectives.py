from __future__ import annotations

import copy
import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from project_manager_api.api.retrospective_schemas import RetrospectiveCreate, RetrospectiveUpdate
from project_manager_api.db.models import (
    AuditLog,
    ChangeProposal,
    ImportRecord,
    MilestoneRuntimeState,
    Project,
    ProjectChangeSet,
    ProjectVersion,
    RetrospectiveReport,
)
from project_manager_api.services.errors import (
    ConfigurationError,
    ConflictError,
    NotFoundError,
    ServiceError,
)
from project_manager_api.services.milestone_runtime import effective_project_snapshot
from project_manager_api.services.projects import ProjectService
from project_manager_api.settings import AppSettings


def _invalid(message: str) -> None:
    error = ServiceError(message)
    error.status_code = 422
    raise error


def _iso(value: datetime | None) -> str | None:
    return _utc(value).isoformat() if value else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def _plan(snapshot: dict[str, Any], code: str, plan_name: str | None = None) -> Any:
    milestone = next((m for m in snapshot.get("milestones", []) if m["code"] == code), None)
    selected = next(
        (
            p
            for p in snapshot.get("plan_versions", [])
            if p["name"] == (plan_name or snapshot.get("active_plan_name"))
        ),
        None,
    )
    return (
        copy.deepcopy(selected.get("milestones", {}).get(milestone["name"]))
        if milestone and selected
        else None
    )


def _milestones(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {item["code"]: item for item in snapshot.get("milestones", [])}


def _delta(actual: Any, plan: Any) -> int | None:
    if (
        not actual
        or not plan
        or actual.get("state") != "scheduled"
        or plan.get("state") != "scheduled"
    ):
        return None
    if not actual.get("end_date") or not plan.get("end_date"):
        return None
    return (date.fromisoformat(actual["end_date"]) - date.fromisoformat(plan["end_date"])).days


class RetrospectiveService:
    def __init__(self, session: Session, actor_id: str, settings: AppSettings):
        self.session = session
        self.actor_id = actor_id
        self.settings = settings
        self.projects = ProjectService(session, actor_id)

    def _configuration(self) -> dict[str, Any]:
        return dict(
            yaml.safe_load(self.settings.retrospective_config_path.read_text(encoding="utf-8"))
        )

    def _categories(self) -> list[str]:
        data = self._configuration()
        categories = data.get("reason_categories") if isinstance(data, dict) else None
        if (
            not isinstance(categories, list)
            or not categories
            or not all(isinstance(c, str) and c.strip() for c in categories)
        ):
            raise ConfigurationError("retrospective reason_categories must be a nonempty list")
        return list(dict.fromkeys(c.strip() for c in categories))

    def options(self, project_id: uuid.UUID) -> dict[str, Any]:
        self.projects._require_project(project_id, manager=True)
        return {
            "baselines": [
                {"version_number": v.version_number, "plan_name": p["name"]}
                for v in self._versions(project_id)
                for p in sorted(
                    v.snapshot.get("plan_versions", []),
                    key=lambda p: p["name"] != self._configuration()["original_plan_name"],
                )
            ],
            "reason_categories": self._categories(),
        }

    def _versions(self, project_id: uuid.UUID) -> list[ProjectVersion]:
        return list(
            self.session.scalars(
                select(ProjectVersion)
                .where(ProjectVersion.project_id == project_id)
                .order_by(ProjectVersion.version_number)
            )
        )

    def list_reports(self, project_id: uuid.UUID) -> list[dict[str, Any]]:
        self.projects._require_project(project_id, manager=True)
        return [
            _report(r)
            for r in self.session.scalars(
                select(RetrospectiveReport)
                .where(RetrospectiveReport.project_id == project_id)
                .order_by(RetrospectiveReport.report_number.desc())
            )
        ]

    def _require_report(self, report_id: uuid.UUID, lock: bool = False) -> RetrospectiveReport:
        report = self.session.get(RetrospectiveReport, report_id)
        if report is None:
            raise NotFoundError("retrospective report not found")
        self.projects._require_project(report.project_id, manager=True, lock=lock)
        if lock:
            self._sqlite_project_lock(report.project_id)
            self.projects._require_project(report.project_id, manager=True)
            self.session.refresh(report)
        return report

    def _sqlite_project_lock(self, project_id: uuid.UUID) -> None:
        # SQLite ignores FOR UPDATE. A no-op write obtains its transaction write lock
        # before reading evidence, so a concurrent publication cannot pass confirmation.
        bind = self.session.get_bind()
        if bind.dialect.name == "sqlite":
            self.session.execute(
                update(Project)
                .where(Project.id == project_id)
                .values(
                    current_version_number=Project.current_version_number,
                    updated_at=Project.updated_at,
                )
            )

    def get(self, report_id: uuid.UUID) -> dict[str, Any]:
        return _report(self._require_report(report_id))

    def create(self, project_id: uuid.UUID, payload: RetrospectiveCreate) -> dict[str, Any]:
        self.projects._require_project(project_id, manager=True, lock=True)
        self._sqlite_project_lock(project_id)
        self.projects._require_project(project_id, manager=True)
        versions = self._versions(project_id)
        if not versions:
            raise ConflictError("project has no published version")
        previous = (
            self._require_report(payload.supersedes_report_id)
            if payload.supersedes_report_id
            else None
        )
        if previous and previous.project_id != project_id:
            _invalid("revisions must reference a report from the same project")
        baseline = previous.facts["baseline"] if previous else {}
        number = (
            payload.baseline_version_number
            or baseline.get("version_number")
            or versions[0].version_number
        )
        version = next((v for v in versions if v.version_number == number), None)
        if version is None:
            _invalid("baseline version does not belong to this project")
        assert version is not None
        plans = version.snapshot.get("plan_versions", [])
        if not plans:
            raise ConflictError("baseline version has no plans")
        plan_name = (
            payload.baseline_plan_name
            or baseline.get("plan_name")
            or next(
                (
                    p["name"]
                    for p in plans
                    if p["name"] == self._configuration()["original_plan_name"]
                ),
                plans[0]["name"],
            )
        )
        if not any(p["name"] == plan_name for p in plans):
            _invalid("baseline plan does not exist in the selected version")
        facts, fingerprint = self._facts(
            project_id, {"version_number": number, "plan_name": plan_name}
        )
        review: dict[str, Any] = {
            "baseline_confirmed": False,
            "baseline_note": "",
            "reason_reviews": [],
            "improvements": [],
        }
        if previous:
            review = copy.deepcopy(previous.review)
            review["baseline_confirmed"] = False
            for reason in review["reason_reviews"]:
                reason["status"] = "pending"
        else:
            for milestone in facts["milestones"]:
                reasons = list(
                    dict.fromkeys(
                        event["reason"]
                        for event in facts["timeline"]
                        if event["milestone_code"] == milestone["code"]
                        and event["reason"]
                        and event["effective"]
                    )
                )
                if reasons:
                    review["reason_reviews"].append(
                        {
                            "milestone_code": milestone["code"],
                            "category": self._categories()[0],
                            "confirmed_reason": "；".join(reasons),
                            "evidence": "",
                            "fact_confirmed_by": "",
                            "confirmation_source": "原始申请理由摘录，待人工核实",
                            "status": "pending",
                        }
                    )
        report = RetrospectiveReport(
            project_id=project_id,
            report_number=(
                self.session.scalar(
                    select(func.max(RetrospectiveReport.report_number)).where(
                        RetrospectiveReport.project_id == project_id
                    )
                )
                or 0
            )
            + 1,
            supersedes_report_id=payload.supersedes_report_id,
            facts=facts,
            review=review,
            facts_sha256=fingerprint,
            created_by=self.actor_id,
        )
        self.session.add(report)
        self.session.flush()
        self.projects._audit(
            project_id, "retrospective.created", "retrospective_report", str(report.id)
        )
        return _report(report)

    def save(self, report_id: uuid.UUID, payload: RetrospectiveUpdate) -> dict[str, Any]:
        report = self._require_report(report_id, lock=True)
        self._check_draft(report, payload.expected_revision)
        codes = {m["code"] for m in report.facts["milestones"]}
        events = {e["id"]: e for e in report.facts["timeline"]}
        for reason in payload.reason_reviews:
            if reason.milestone_code not in codes or (
                reason.category and reason.category not in self._categories()
            ):
                _invalid("reason review references an unknown milestone or category")
        for item in payload.improvements:
            if item.milestone_code is not None and item.milestone_code not in codes:
                _invalid("improvement references an unknown milestone")
            if any(event_id not in events for event_id in item.source_event_ids):
                _invalid("improvement references an unknown evidence event")
            if item.milestone_code and any(
                events[event_id]["milestone_code"] != item.milestone_code
                for event_id in item.source_event_ids
            ):
                _invalid("improvement evidence does not belong to the selected milestone")
        review = payload.model_dump(mode="json", exclude={"expected_revision"})
        for item in review["reason_reviews"] + review["improvements"]:
            item["recorded_by"] = self.actor_id
        self._update(report, payload.expected_revision, review=review)
        self.projects._audit(
            report.project_id,
            "retrospective.review_updated",
            "retrospective_report",
            str(report.id),
            after={"revision": report.revision, "recorded_by": self.actor_id, "review": review},
        )
        return _report(report)

    @staticmethod
    def _check_draft(report: RetrospectiveReport, expected_revision: int) -> None:
        if report.status != "draft":
            raise ConflictError("confirmed retrospective reports are immutable; create a revision")
        if report.revision != expected_revision:
            raise ConflictError("retrospective revision is stale")

    def _update(self, report: RetrospectiveReport, expected: int, **values: Any) -> None:
        result = self.session.scalar(
            update(RetrospectiveReport)
            .where(
                RetrospectiveReport.id == report.id,
                RetrospectiveReport.revision == expected,
                RetrospectiveReport.status == "draft",
            )
            .values(revision=expected + 1, **values)
            .returning(RetrospectiveReport.id)
            .execution_options(synchronize_session=False)
        )
        if result is None:
            raise ConflictError("retrospective revision is stale")
        self.session.refresh(report)

    def confirm(self, report_id: uuid.UUID, expected_revision: int) -> dict[str, Any]:
        report = self._require_report(report_id, lock=True)
        self._check_draft(report, expected_revision)
        if not report.review["baseline_confirmed"] or not report.review["baseline_note"].strip():
            raise ConflictError("confirm the original baseline and supporting note first")
        _, fingerprint = self._facts(report.project_id, report.facts["baseline"])
        if fingerprint != report.facts_sha256:
            raise ConflictError(
                "project evidence changed after report generation; create a new draft"
            )
        self._update(
            report,
            expected_revision,
            status="confirmed",
            confirmed_by=self.actor_id,
            confirmed_at=datetime.now(UTC),
        )
        self.projects._audit(
            report.project_id,
            "retrospective.confirmed",
            "retrospective_report",
            str(report.id),
            after={"revision": report.revision},
        )
        return _report(report)

    def _facts(self, project_id: uuid.UUID, baseline: dict[str, Any]) -> tuple[dict[str, Any], str]:
        versions = self._versions(project_id)
        proposals = list(
            self.session.scalars(
                select(ChangeProposal).where(ChangeProposal.project_id == project_id)
            )
        )
        imports = list(
            self.session.scalars(select(ImportRecord).where(ImportRecord.project_id == project_id))
        )
        sets = list(
            self.session.scalars(
                select(ProjectChangeSet).where(ProjectChangeSet.project_id == project_id)
            )
        )
        audits = list(
            self.session.scalars(
                select(AuditLog).where(
                    AuditLog.project_id == project_id, ~AuditLog.action.like("retrospective.%")
                )
            )
        )
        states = list(
            self.session.scalars(
                select(MilestoneRuntimeState).where(MilestoneRuntimeState.project_id == project_id)
            )
        )
        # Exclude report operations and unrelated issue/member audit traffic from the hash.
        relevant_audits = [
            a
            for a in audits
            if a.action.startswith(("import.", "change_proposal.", "project_change_set."))
        ]
        source_rows = [
            [
                {column.name: getattr(row, column.name) for column in row.__table__.columns}
                for row in sorted(rows, key=lambda row: str(row.id))
            ]
            for rows in (versions, proposals, imports, sets, relevant_audits, states)
        ]
        fingerprint = _hash(source_rows)
        base_version = next(v for v in versions if v.version_number == baseline["version_number"])
        timeline: list[dict[str, Any]] = []
        warnings = [
            f"自然日口径，业务时区{self.settings.app_timezone}；同日生效按完成日前/当日计划处理。节点偏差不能累加或取最大值作为项目总延期。",
            "导入前计划行的真实发生时间、审批链及生效次数未采集，需人工核对。",
        ]
        formal: dict[str, Any] = {}
        overrides: dict[str, dict[str, Any]] = {}
        history: dict[str, list[tuple[datetime | None, Any]]] = {}
        counts: dict[str, int] = {}
        ever: dict[str, Any] = {}

        def effective() -> dict[str, Any]:
            result = copy.deepcopy(formal)
            for code, values in overrides.items():
                milestone = _milestones(result).get(code)
                if not milestone:
                    continue
                if "completion" in values:
                    milestone["actual_completion"] = copy.deepcopy(values["completion"])
                if "schedule" in values and values.get("plan_name") == result.get(
                    "active_plan_name"
                ):
                    plan = next(
                        (p for p in result["plan_versions"] if p["name"] == values["plan_name"]),
                        None,
                    )
                    if plan and milestone["name"] in plan["milestones"]:
                        plan["milestones"][milestone["name"]] = copy.deepcopy(values["schedule"])
            return result

        def event(
            identifier: str,
            source: str,
            kind: str,
            code: str,
            before: Any,
            after: Any,
            occurred: datetime | None,
            recorded: datetime,
            status: str,
            is_effective: bool,
            reason: str | None = None,
            submitted: str | None = None,
            resolved: str | None = None,
            refs: list[str] | None = None,
        ) -> None:
            timeline.append(
                {
                    "id": identifier,
                    "source": source,
                    "kind": kind,
                    "milestone_code": code,
                    "effective": is_effective,
                    "occurred_at": _iso(occurred),
                    "recorded_at": _iso(recorded),
                    "status": status,
                    "before": copy.deepcopy(before),
                    "after": copy.deepcopy(after),
                    "reason": reason,
                    "submitted_by": submitted,
                    "resolved_by": resolved,
                    "evidence_refs": refs or [],
                }
            )

        legacy: dict[uuid.UUID, ChangeProposal] = {}
        for proposal in proposals:
            if proposal.status != "approved":
                continue
            candidate = next(
                (v for v in versions if v.version_number == proposal.base_version_number + 1), None
            )
            approval_audit = next(
                (
                    a
                    for a in audits
                    if a.action == "change_proposal.approved" and a.entity_id == str(proposal.id)
                ),
                None,
            )
            linked_number = (
                (approval_audit.after_value or {}).get("version_number") if approval_audit else None
            )
            if candidate is None:
                continue
            candidate_value = (
                _milestones(candidate.snapshot)
                .get(proposal.milestone_code, {})
                .get("actual_completion")
                if proposal.proposal_kind == "completed"
                else _plan(candidate.snapshot, proposal.milestone_code)
            )
            if linked_number == candidate.version_number or (
                proposal.resolved_at
                and candidate_value == proposal.after_value
                and _utc(proposal.created_at)
                <= _utc(candidate.created_at)
                <= _utc(proposal.resolved_at)
            ):
                legacy[candidate.id] = proposal

        ordered: list[tuple[datetime, int, Any]] = [(_utc(v.created_at), 0, v) for v in versions]
        ordered.extend(
            (_utc(p.resolved_at or p.created_at), 1, p)
            for p in proposals
            if p.status == "approved" and p.id not in {p.id for p in legacy.values()}
        )
        for event_time, _, row in sorted(
            ordered, key=lambda item: (item[0], item[1], str(item[2].id))
        ):
            occurred: datetime | None = event_time
            before = effective()
            if isinstance(row, ProjectVersion):
                change_set = next(
                    (
                        c
                        for c in sets
                        if c.status == "published"
                        and c.base_version_number + 1 == row.version_number
                    ),
                    None,
                )
                import_record = next(
                    (
                        i
                        for i in imports
                        if i.status == "published"
                        and i.base_version_number + 1 == row.version_number
                        and i.draft == row.snapshot
                    ),
                    None,
                )
                audit = next(
                    (
                        a
                        for a in audits
                        if (a.action == "import.published" and a.entity_id == str(row.id))
                        or (
                            change_set
                            and a.action == "project_change_set.published"
                            and a.entity_id == str(change_set.id)
                        )
                    ),
                    None,
                )
                legacy_proposal = legacy.get(row.id)
                if legacy_proposal and legacy_proposal.resolved_at:
                    occurred = _utc(legacy_proposal.resolved_at)
                elif audit:
                    occurred = _utc(audit.created_at)
                elif change_set and change_set.resolved_at:
                    occurred = _utc(change_set.resolved_at)
                source = (
                    "mobile"
                    if legacy_proposal
                    and legacy_proposal.submitted_by_actor_id.startswith("mobile:")
                    else "admin_web"
                    if legacy_proposal
                    else "admin_web"
                    if change_set
                    else "excel"
                    if import_record or (audit and audit.action == "import.published")
                    else "unknown"
                )
                diff = (
                    change_set.diff if change_set else import_record.diff if import_record else []
                )
                for change in diff or []:
                    path = change.get("path", "")
                    if not path.startswith("runtime_state[") or not change.get("before"):
                        continue
                    code, field = path.removeprefix("runtime_state[").split("].", 1)
                    value = change["before"].get("value")
                    prior = _milestones(before).get(code)
                    if prior is not None and field == "actual_completion":
                        prior["actual_completion"] = copy.deepcopy(value)
                    elif prior is not None and field == "schedule":
                        prior_plan = next(
                            (
                                p
                                for p in before.get("plan_versions", [])
                                if p["name"] == change["before"].get("plan_name")
                            ),
                            None,
                        )
                        if prior_plan and prior_plan["name"] == before.get("active_plan_name"):
                            prior_plan["milestones"][prior["name"]] = copy.deepcopy(value)
                            if not history.get(code) or history[code][-1][1] != value:
                                history.setdefault(code, []).append((None, value))
                formal = copy.deepcopy(row.snapshot)
                for change in diff or []:
                    path = change.get("path", "")
                    if path.startswith("runtime_state["):
                        code, field = path.removeprefix("runtime_state[").split("].", 1)
                        if code in overrides:
                            if field == "schedule":
                                overrides[code].pop("schedule", None)
                                overrides[code].pop("plan_name", None)
                            elif field == "actual_completion":
                                overrides[code].pop("completion", None)
                overrides = {
                    code: values
                    for code, values in overrides.items()
                    if code in _milestones(formal)
                }
                after = effective()
                if row.version_number == versions[0].version_number:
                    for code in _milestones(after):
                        history.setdefault(code, []).append((occurred, _plan(after, code)))
                        for plan in formal.get("plan_versions", []):
                            if plan["name"] != base_version.snapshot.get("plan_versions", [{}])[
                                0
                            ].get("name"):
                                event(
                                    f"history:{row.id}:{code}:{plan['name']}",
                                    "pre_import_history",
                                    "schedule",
                                    code,
                                    None,
                                    _plan(formal, code, plan["name"]),
                                    None,
                                    row.created_at,
                                    "uncollected",
                                    False,
                                    refs=[f"project_version:{row.id}"],
                                )
                else:
                    for code in sorted(set(_milestones(before)) | set(_milestones(after))):
                        old, new = _milestones(before).get(code), _milestones(after).get(code)
                        if old is None or new is None:
                            event(
                                f"version:{row.id}:{code}:scope",
                                source,
                                "scope",
                                code,
                                old,
                                new,
                                occurred,
                                row.created_at,
                                "published",
                                True,
                                change_set.reason
                                if change_set
                                else legacy_proposal.reason
                                if legacy_proposal
                                else None,
                                change_set.submitted_by_actor_id
                                if change_set
                                else legacy_proposal.submitted_by_actor_id
                                if legacy_proposal
                                else None,
                                audit.actor_id
                                if audit
                                else legacy_proposal.approved_by_actor_id
                                if legacy_proposal
                                else None,
                                [f"project_version:{row.id}"],
                            )
                        old_plan, new_plan = _plan(before, code), _plan(after, code)
                        if old_plan != new_plan:
                            event(
                                f"version:{row.id}:{code}:schedule",
                                source,
                                "schedule",
                                code,
                                old_plan,
                                new_plan,
                                occurred,
                                row.created_at,
                                "published",
                                True,
                                change_set.reason
                                if change_set
                                else legacy_proposal.reason
                                if legacy_proposal
                                else None,
                                change_set.submitted_by_actor_id
                                if change_set
                                else legacy_proposal.submitted_by_actor_id
                                if legacy_proposal
                                else None,
                                audit.actor_id
                                if audit
                                else legacy_proposal.approved_by_actor_id
                                if legacy_proposal
                                else None,
                                [f"project_version:{row.id}"],
                            )
                            if old is not None and new is not None:
                                counts[code] = counts.get(code, 0) + 1
                            history.setdefault(code, []).append((occurred, new_plan))
                        old_actual = old.get("actual_completion") if old else None
                        new_actual = new.get("actual_completion") if new else None
                        if old_actual != new_actual:
                            event(
                                f"version:{row.id}:{code}:completion",
                                source,
                                "completion",
                                code,
                                old_actual,
                                new_actual,
                                occurred,
                                row.created_at,
                                "published",
                                True,
                                change_set.reason
                                if change_set
                                else legacy_proposal.reason
                                if legacy_proposal
                                else None,
                                change_set.submitted_by_actor_id
                                if change_set
                                else legacy_proposal.submitted_by_actor_id
                                if legacy_proposal
                                else None,
                                audit.actor_id
                                if audit
                                else legacy_proposal.approved_by_actor_id
                                if legacy_proposal
                                else None,
                                [f"project_version:{row.id}"],
                            )
                ever.update(_milestones(after))
            else:
                proposal = row
                occurred = _utc(proposal.resolved_at) if proposal.resolved_at else None
                source = (
                    "mobile"
                    if proposal.submitted_by_actor_id.startswith("mobile:")
                    else "admin_web"
                )
                kind = "completion" if proposal.proposal_kind == "completed" else "schedule"
                code = proposal.milestone_code
                exists = code in _milestones(formal)
                values = overrides.setdefault(code, {})
                values[kind] = copy.deepcopy(proposal.after_value)
                if kind == "schedule":
                    values["plan_name"] = next(
                        (
                            v.snapshot.get("active_plan_name")
                            for v in versions
                            if v.version_number == proposal.base_version_number
                        ),
                        None,
                    )
                after = effective()
                old_value = (
                    _plan(before, code)
                    if kind == "schedule"
                    else _milestones(before).get(code, {}).get("actual_completion")
                )
                new_value = (
                    _plan(after, code)
                    if kind == "schedule"
                    else _milestones(after).get(code, {}).get("actual_completion")
                )
                changed = exists and old_value != new_value
                event(
                    f"proposal:{proposal.id}",
                    source,
                    kind,
                    code,
                    proposal.before_value,
                    proposal.after_value,
                    occurred,
                    proposal.created_at,
                    proposal.status,
                    changed,
                    proposal.reason,
                    proposal.submitted_by_actor_id,
                    proposal.approved_by_actor_id,
                    [f"change_proposal:{proposal.id}"],
                )
                if changed and kind == "schedule":
                    counts[code] = counts.get(code, 0) + 1
                    history.setdefault(code, []).append((occurred, new_value))
                ever.update(_milestones(after))
        for proposal in proposals:
            if proposal.status != "approved":
                event(
                    f"proposal:{proposal.id}",
                    "mobile"
                    if proposal.submitted_by_actor_id.startswith("mobile:")
                    else "admin_web",
                    "completion" if proposal.proposal_kind == "completed" else "schedule",
                    proposal.milestone_code,
                    proposal.before_value,
                    proposal.after_value,
                    proposal.resolved_at,
                    proposal.created_at,
                    proposal.status,
                    False,
                    proposal.reason,
                    proposal.submitted_by_actor_id,
                    proposal.approved_by_actor_id,
                    [f"change_proposal:{proposal.id}"],
                )
        # Persisted runtime supplies current facts; replay supplies pre-completion plans and counts.
        current = effective_project_snapshot(self.session, project_id, versions[-1].snapshot)
        base_codes = _milestones(base_version.snapshot)
        current_codes = _milestones(current)
        ever.update(base_codes)
        ever.update(current_codes)
        output = []
        timezone = ZoneInfo(self.settings.app_timezone)
        for code, milestone in ever.items():
            item_warnings: list[str] = []
            original = _plan(base_version.snapshot, code, baseline["plan_name"])
            latest = _plan(current, code)
            actual = current_codes.get(code, milestone).get("actual_completion")
            completed = bool(
                actual and actual.get("state") == "scheduled" and actual.get("end_date")
            )
            variance_plan = latest
            if completed:
                actual_date = date.fromisoformat(actual["end_date"])
                candidates = [
                    (when, plan)
                    for when, plan in history.get(code, [])
                    if when is not None and _utc(when).astimezone(timezone).date() <= actual_date
                ]
                unknown_history = any(when is None for when, _ in history.get(code, []))
                variance_plan = candidates[-1][1] if candidates and not unknown_history else None
                if variance_plan is None:
                    item_warnings.append("无法重建实际完成时已生效计划，调整后偏差不计算。")
                if any(
                    event["milestone_code"] == code
                    and event["kind"] == "schedule"
                    and event["effective"]
                    and event["occurred_at"]
                    and datetime.fromisoformat(event["occurred_at"]).astimezone(timezone).date()
                    > actual_date
                    for event in timeline
                ):
                    item_warnings.append("实际完成后仍有计划生效变更；偏差按完成时计划计算。")
            status = (
                "removed"
                if code not in current_codes
                else "not_applicable"
                if latest and latest.get("state") == "not_applicable"
                else "completed"
                if completed
                else "incomplete"
            )
            if original is None or original.get("state") != "scheduled":
                item_warnings.append("原始日期缺失或不适用，原始偏差不计算。")
            if status == "incomplete":
                item_warnings.append("节点未完成，不能按零延期计算。")
            output.append(
                {
                    "code": code,
                    "name": milestone["name"],
                    "original_plan": original,
                    "latest_plan": latest,
                    "variance_plan": variance_plan,
                    "actual_completion": actual,
                    "original_variance_days": _delta(actual, original),
                    "adjusted_variance_days": _delta(actual, variance_plan),
                    "effective_adjustment_count": counts.get(code, 0),
                    "imported_plan_rows_count": len(versions[0].snapshot.get("plan_versions", []))
                    if code in _milestones(versions[0].snapshot)
                    else 0,
                    "status": status,
                    "scope_change": "removed"
                    if code not in current_codes
                    else "added"
                    if code not in base_codes
                    else None,
                    "assignments": milestone.get("assignments", {}),
                    "warnings": item_warnings,
                }
            )
        facts = {
            "cutoff_at": _iso(datetime.now(UTC)),
            "project_version_number": versions[-1].version_number,
            "baseline": baseline,
            "date_basis": "calendar_days",
            "effective_snapshot": {
                key: copy.deepcopy(current.get(key))
                for key in ("project", "milestones", "plan_versions", "active_plan_name")
            },
            "milestones": output,
            "timeline": sorted(
                timeline, key=lambda e: (e["occurred_at"] or "", e["recorded_at"], e["id"])
            ),
            "warnings": warnings,
        }
        return facts, fingerprint


def _report(report: RetrospectiveReport) -> dict[str, Any]:
    return {
        "id": str(report.id),
        "project_id": str(report.project_id),
        "report_number": report.report_number,
        "revision": report.revision,
        "status": report.status,
        "created_at": _iso(report.created_at),
        "confirmed_at": _iso(report.confirmed_at),
        "created_by": report.created_by,
        "confirmed_by": report.confirmed_by,
        "supersedes_report_id": str(report.supersedes_report_id)
        if report.supersedes_report_id
        else None,
        "facts": copy.deepcopy(report.facts),
        "review": copy.deepcopy(report.review),
    }
