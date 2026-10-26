from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from fastapi.testclient import TestClient

from project_manager_api.api.app import create_app
from project_manager_api.db.base import Base
from project_manager_api.db.models import (
    AuditLog,
    ChangeProposal,
    MilestoneRuntimeState,
    Project,
    ProjectMembership,
    ProjectVersion,
)
from project_manager_api.settings import AppSettings

ROOT = Path(__file__).resolve().parents[3]
HEADERS = {"Authorization": "Bearer retrospective-test"}


def window(day: int) -> dict[str, Any]:
    return {
        "state": "scheduled",
        "start_date": f"2026-06-{day:02}",
        "end_date": f"2026-06-{day:02}",
    }


def snapshot() -> dict[str, Any]:
    return {
        "template_id": "test",
        "template_version": "1",
        "document_version": "1",
        "active_plan_name": "变更计划1",
        "project": {"code": "RET", "name": "复盘测试"},
        "milestones": [
            {
                "code": "M01",
                "name": "节点",
                "actual_completion": window(14),
                "assignments": {"R": ["张三"]},
            }
        ],
        "plan_versions": [
            {"name": "原计划", "milestones": {"节点": window(1)}},
            {"name": "变更计划1", "milestones": {"节点": window(5)}},
        ],
    }


@pytest.fixture
def retrospective() -> Any:
    with TemporaryDirectory(dir=ROOT / "tmp") as directory:
        settings = AppSettings(
            database_url=f"sqlite:///{Path(directory) / 'ret.sqlite'}",
            manifest_paths=[],
            import_storage_path=Path(directory),
            max_import_size_bytes=100000,
            admin_api_token="retrospective-test",
        )
        app = create_app(settings)
        Base.metadata.create_all(app.state.engine)
        with app.state.session_factory() as session:
            project = Project(code="RET", name="复盘测试", current_version_number=1)
            session.add(project)
            session.flush()
            project_id = str(project.id)
            session.add(
                ProjectMembership(project_id=project.id, actor_id="pm-001", role="project_manager")
            )
            session.add(
                ProjectVersion(
                    project_id=project.id,
                    version_number=1,
                    template_id="test",
                    template_version="1",
                    document_version="1",
                    content_sha256="a" * 64,
                    snapshot=snapshot(),
                    created_at=datetime(2026, 6, 1, tzinfo=UTC),
                )
            )
            for day, before, after in [(2, 5, 10), (3, 10, 15)]:
                proposal = ChangeProposal(
                    project_id=project.id,
                    milestone_code="M01",
                    proposal_kind="schedule",
                    target_path="plan_versions",
                    base_version_number=1,
                    before_value=window(before),
                    after_value=window(after),
                    reason="资源冲突",
                    status="approved",
                    submitted_by_actor_id="mobile:test",
                    approved_by_actor_id="pm-001",
                    created_at=datetime(2026, 6, day, tzinfo=UTC),
                    resolved_at=datetime(2026, 6, day, tzinfo=UTC),
                )
                session.add(proposal)
                session.flush()
                session.add(
                    AuditLog(
                        project_id=project.id,
                        actor_id="pm-001",
                        source="admin_web",
                        action="change_proposal.approved",
                        entity_type="change_proposal",
                        entity_id=str(proposal.id),
                        before_value=window(before),
                        after_value=window(after),
                    )
                )
            session.add(
                MilestoneRuntimeState(
                    project_id=project.id,
                    milestone_code="M01",
                    schedule=window(15),
                    schedule_plan_name="变更计划1",
                    schedule_revision=2,
                    actual_completion=None,
                    completion_revision=0,
                )
            )
            session.commit()
        with TestClient(app) as client:
            yield client, project_id
        app.state.engine.dispose()


def write(client: TestClient, method: str, path: str, body: dict[str, Any]) -> Any:
    return client.request(
        method,
        f"/api/v1{path}",
        headers={**HEADERS, "X-Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )


def test_retrospective_original_latest_dates_and_all_source_timeline(retrospective: Any) -> None:
    client, project = retrospective
    options = client.get(f"/api/v1/projects/{project}/retrospective-options", headers=HEADERS)
    assert options.status_code == 200
    assert options.json()["baselines"][0] == {"version_number": 1, "plan_name": "原计划"}
    response = write(client, "POST", f"/projects/{project}/retrospectives", {})
    assert response.status_code == 201, response.text
    report = response.json()
    milestone = report["facts"]["milestones"][0]
    assert milestone["original_variance_days"] == 13
    assert milestone["adjusted_variance_days"] == -1
    assert milestone["effective_adjustment_count"] == 2
    timeline = report["facts"]["timeline"]
    assert len([item for item in timeline if item["source"] == "mobile" and item["effective"]]) == 2
    assert any(
        item["source"] == "pre_import_history" and item["occurred_at"] is None for item in timeline
    )
    assert report["review"]["baseline_confirmed"] is False


def test_retrospective_confirmation_revision_snapshot_and_revision_copy(retrospective: Any) -> None:
    client, project = retrospective
    draft = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    path = f"/retrospectives/{draft['id']}"
    assert write(client, "POST", path + "/confirm", {"expected_revision": 1}).status_code == 409
    review = {
        "expected_revision": 1,
        "baseline_confirmed": True,
        "baseline_note": "已核对原始规格书",
        "reason_reviews": [],
        "improvements": [],
    }
    saved = write(client, "PATCH", path, review)
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 2
    assert write(client, "PATCH", path, review).status_code == 409
    confirmed = write(client, "POST", path + "/confirm", {"expected_revision": 2})
    assert confirmed.status_code == 200, confirmed.text
    frozen = confirmed.json()
    assert frozen["status"] == "confirmed"
    assert write(client, "PATCH", path, {**review, "expected_revision": 3}).status_code == 409
    revision = write(
        client, "POST", f"/projects/{project}/retrospectives", {"supersedes_report_id": draft["id"]}
    )
    assert revision.status_code == 201, revision.text
    assert revision.json()["review"]["baseline_confirmed"] is False
    assert client.get(f"/api/v1{path}", headers=HEADERS).json() == frozen


def test_retrospective_stale_facts_and_project_isolation(retrospective: Any) -> None:
    client, project = retrospective
    draft = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    path = f"/retrospectives/{draft['id']}"
    saved = write(
        client,
        "PATCH",
        path,
        {
            "expected_revision": 1,
            "baseline_confirmed": True,
            "baseline_note": "核对",
            "reason_reviews": [],
            "improvements": [],
        },
    )
    assert saved.status_code == 200
    with client.app.state.session_factory() as session:
        state = session.query(MilestoneRuntimeState).one()
        state.schedule = window(16)
        state.schedule_revision += 1
        session.commit()
    assert write(client, "POST", path + "/confirm", {"expected_revision": 2}).status_code == 409
    with client.app.state.session_factory() as session:
        membership = session.query(ProjectMembership).one()
        membership.actor_id = "someone-else"
        session.commit()
    assert client.get(f"/api/v1{path}", headers=HEADERS).status_code == 403


def test_retrospective_rejects_blank_and_unknown_references(retrospective: Any) -> None:
    client, project = retrospective
    draft = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    path = f"/retrospectives/{draft['id']}"
    payload = {
        "expected_revision": 1,
        "baseline_confirmed": True,
        "baseline_note": "   ",
        "reason_reviews": [],
        "improvements": [],
    }
    assert write(client, "PATCH", path, payload).status_code == 422
    payload["baseline_note"] = "核对"
    payload["improvements"] = [
        {
            "milestone_code": "M404",
            "source_event_ids": [],
            "scenario": "场景",
            "action": "行动",
            "proposed_owner": "张三",
            "acceptance": "检查",
        }
    ]
    assert write(client, "PATCH", path, payload).status_code == 422


def test_post_completion_changes_do_not_erase_variance(retrospective: Any) -> None:
    client, project = retrospective
    with client.app.state.session_factory() as session:
        proposal = ChangeProposal(
            project_id=uuid.UUID(project),
            milestone_code="M01",
            proposal_kind="schedule",
            target_path="schedule",
            base_version_number=1,
            before_value=window(15),
            after_value=window(20),
            reason="完成后补改计划",
            status="approved",
            submitted_by_actor_id="mobile:test",
            approved_by_actor_id="pm-001",
            created_at=datetime(2026, 6, 16, tzinfo=UTC),
            resolved_at=datetime(2026, 6, 16, tzinfo=UTC),
        )
        session.add(proposal)
        state = session.query(MilestoneRuntimeState).one()
        state.schedule = window(20)
        state.schedule_revision += 1
        session.commit()
    response = write(client, "POST", f"/projects/{project}/retrospectives", {})
    milestone = response.json()["facts"]["milestones"][0]
    assert milestone["latest_plan"]["end_date"] == "2026-06-20"
    assert milestone["variance_plan"]["end_date"] == "2026-06-15"
    assert milestone["adjusted_variance_days"] == -1
    assert milestone["warnings"]


def test_runtime_reset_formal_publication_and_no_duplicate_audits(retrospective: Any) -> None:
    import copy

    from project_manager_api.db.models import ProjectChangeSet

    client, project = retrospective
    with client.app.state.session_factory() as session:
        initial = session.query(ProjectVersion).one()
        changed = copy.deepcopy(initial.snapshot)
        # Formal baseline's 5 -> 12 clears a runtime override of 15: effective 15 -> 12.
        changed["plan_versions"][1]["milestones"]["节点"] = window(12)
        version = ProjectVersion(
            project_id=uuid.UUID(project),
            version_number=2,
            template_id="test",
            template_version="1",
            document_version="1",
            content_sha256="b" * 64,
            snapshot=changed,
            created_at=datetime(2026, 6, 4, tzinfo=UTC),
        )
        session.add(version)
        session.add(
            ProjectChangeSet(
                project_id=uuid.UUID(project),
                base_version_number=1,
                source="admin_web",
                operations=[],
                diff=[
                    {
                        "path": "runtime_state[M01].schedule",
                        "operation": "removed",
                        "before": {"value": window(15), "plan_name": "变更计划1", "revision": 2},
                        "after": None,
                    }
                ],
                reason="统一计划",
                status="published",
                submitted_by_actor_id="pm-001",
                published_by_actor_id="pm-001",
                created_at=datetime(2026, 6, 4, tzinfo=UTC),
                resolved_at=datetime(2026, 6, 4, tzinfo=UTC),
            )
        )
        session.query(MilestoneRuntimeState).one().schedule = None
        session.query(Project).one().current_version_number = 2
        session.commit()
    report = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    milestone = report["facts"]["milestones"][0]
    assert milestone["effective_adjustment_count"] == 3
    assert milestone["latest_plan"]["end_date"] == "2026-06-12"
    events = [
        e
        for e in report["facts"]["timeline"]
        if e["source"] == "admin_web" and e["kind"] == "schedule"
    ]
    assert len(events) == 1
    assert events[0]["before"] == window(15)
    assert events[0]["after"] == window(12)


def test_unpublished_project_na_removed_and_unknown_completion_time(retrospective: Any) -> None:
    import copy

    client, project = retrospective
    with client.app.state.session_factory() as session:
        session.add(Project(code="EMPTY", name="空项目"))
        session.flush()
        empty = session.query(Project).filter(Project.code == "EMPTY").one()
        empty_id = str(empty.id)
        session.add(
            ProjectMembership(project_id=empty.id, actor_id="pm-001", role="project_manager")
        )
        version = session.query(ProjectVersion).one()
        changed = copy.deepcopy(version.snapshot)
        changed["milestones"][0]["actual_completion"] = {
            "state": "tbd",
            "start_date": None,
            "end_date": None,
        }
        changed["plan_versions"][1]["milestones"]["节点"] = {
            "state": "not_applicable",
            "start_date": None,
            "end_date": None,
        }
        changed["milestones"].append(
            {"code": "M02", "name": "新增", "actual_completion": window(1), "assignments": {}}
        )
        changed["plan_versions"][1]["milestones"]["新增"] = window(2)
        version.snapshot = changed
        session.query(MilestoneRuntimeState).delete()
        session.query(ChangeProposal).delete()
        session.commit()
    assert (
        client.get(f"/api/v1/projects/{empty_id}/retrospective-options", headers=HEADERS).json()[
            "baselines"
        ]
        == []
    )
    assert write(client, "POST", f"/projects/{empty_id}/retrospectives", {}).status_code == 409
    report = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    m1, m2 = report["facts"]["milestones"]
    assert m1["status"] == "not_applicable"
    assert m1["original_variance_days"] is None
    assert m2["original_plan"] is None


def test_revision_of_stale_draft_copies_reviews_as_pending(retrospective: Any) -> None:
    client, project = retrospective
    draft = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    review = {
        "expected_revision": 1,
        "baseline_confirmed": True,
        "baseline_note": "基准已核对",
        "reason_reviews": [
            {
                "milestone_code": "M01",
                "category": "其他",
                "confirmed_reason": "资源冲突",
                "evidence": "工作记录",
                "fact_confirmed_by": "张三",
                "confirmation_source": "会议核对",
                "status": "confirmed",
            }
        ],
        "improvements": [],
    }
    assert write(client, "PATCH", f"/retrospectives/{draft['id']}", review).status_code == 200
    revision = write(
        client, "POST", f"/projects/{project}/retrospectives", {"supersedes_report_id": draft["id"]}
    ).json()
    assert revision["review"]["baseline_confirmed"] is False
    assert revision["review"]["reason_reviews"][0]["status"] == "pending"
    assert revision["review"]["reason_reviews"][0]["confirmed_reason"] == "资源冲突"
    old = client.get(f"/api/v1/retrospectives/{draft['id']}", headers=HEADERS).json()
    assert old["review"]["reason_reviews"][0]["status"] == "confirmed"


def test_idempotent_replay_still_requires_current_project_permission(retrospective: Any) -> None:
    client, project = retrospective
    headers = {**HEADERS, "X-Idempotency-Key": "same-request"}
    path = f"/api/v1/projects/{project}/retrospectives"
    first = client.post(path, headers=headers, json={})
    assert first.status_code == 201
    assert client.post(path, headers=headers, json={}).json() == first.json()
    with client.app.state.session_factory() as session:
        session.query(ProjectMembership).one().role = "responsible"
        session.commit()
    assert client.post(path, headers=headers, json={}).status_code == 403


def test_migration_upgrade_and_downgrade_isolated_database(monkeypatch: pytest.MonkeyPatch) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    with TemporaryDirectory(dir=ROOT / "tmp") as directory:
        database_url = f"sqlite:///{Path(directory) / 'migration.sqlite'}"
        monkeypatch.setenv("PROJECT_MANAGER_DATABASE_URL", database_url)
        config = Config(str(ROOT / "apps/api/alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "apps/api/migrations"))
        command.upgrade(config, "head")
        engine = create_engine(database_url)
        assert "retrospective_reports" in inspect(engine).get_table_names()
        assert {"facts", "facts_sha256", "revision", "supersedes_report_id"}.issubset(
            c["name"] for c in inspect(engine).get_columns("retrospective_reports")
        )
        command.downgrade(config, "0012_milestone_runtime_states")
        assert "retrospective_reports" not in inspect(engine).get_table_names()
        command.upgrade(config, "head")
        assert "retrospective_reports" in inspect(engine).get_table_names()
        engine.dispose()


def test_legacy_approved_version_does_not_mask_later_publication(retrospective: Any) -> None:
    import copy

    from project_manager_api.db.models import ImportRecord

    client, project = retrospective
    with client.app.state.session_factory() as session:
        session.query(ChangeProposal).delete()
        session.query(AuditLog).delete()
        session.query(MilestoneRuntimeState).delete()
        first = session.query(ProjectVersion).one()
        v2_snapshot = copy.deepcopy(first.snapshot)
        v2_snapshot["plan_versions"][1]["milestones"]["节点"] = window(10)
        session.add(
            ProjectVersion(
                project_id=uuid.UUID(project),
                version_number=2,
                template_id="test",
                template_version="1",
                document_version="1",
                content_sha256="c" * 64,
                snapshot=v2_snapshot,
                created_at=datetime(2026, 6, 2, 1, tzinfo=UTC),
            )
        )
        proposal = ChangeProposal(
            project_id=uuid.UUID(project),
            milestone_code="M01",
            proposal_kind="schedule",
            target_path="schedule",
            base_version_number=1,
            before_value=window(5),
            after_value=window(10),
            reason="旧审批",
            status="approved",
            submitted_by_actor_id="mobile:legacy",
            approved_by_actor_id="pm-001",
            created_at=datetime(2026, 6, 2, tzinfo=UTC),
            resolved_at=datetime(2026, 6, 2, 1, 0, 1, tzinfo=UTC),
        )
        session.add(proposal)
        session.flush()
        session.add(
            AuditLog(
                project_id=uuid.UUID(project),
                actor_id="pm-001",
                source="admin_web",
                action="change_proposal.approved",
                entity_type="change_proposal",
                entity_id=str(proposal.id),
                after_value={"version_number": 2},
            )
        )
        v3_snapshot = copy.deepcopy(v2_snapshot)
        v3_snapshot["plan_versions"][1]["milestones"]["节点"] = window(20)
        session.add(
            ProjectVersion(
                project_id=uuid.UUID(project),
                version_number=3,
                template_id="test",
                template_version="1",
                document_version="1",
                content_sha256="d" * 64,
                snapshot=v3_snapshot,
                created_at=datetime(2026, 6, 3, tzinfo=UTC),
            )
        )
        session.add(
            ImportRecord(
                project_id=uuid.UUID(project),
                filename="fixture.xlsx",
                source_sha256="e" * 64,
                object_key="fixture",
                status="published",
                base_version_number=2,
                draft=v3_snapshot,
                diff=[],
            )
        )
        session.query(Project).one().current_version_number = 3
        session.commit()
    report = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    milestone = report["facts"]["milestones"][0]
    assert milestone["effective_adjustment_count"] == 2
    assert milestone["variance_plan"] == window(20)
    assert milestone["adjusted_variance_days"] == -6
    events = [e for e in report["facts"]["timeline"] if e["effective"] and e["kind"] == "schedule"]
    assert len(events) == 2
    assert [e["source"] for e in events] == ["mobile", "excel"]


def test_pending_reasons_and_recorded_by_are_server_controlled(retrospective: Any) -> None:
    client, project = retrospective
    draft = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    path = f"/retrospectives/{draft['id']}"
    payload = {
        "expected_revision": 1,
        "baseline_confirmed": False,
        "baseline_note": "",
        "reason_reviews": [{"milestone_code": "M01", "category": "", "status": "pending"}],
        "improvements": [],
    }
    saved = write(client, "PATCH", path, payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["review"]["reason_reviews"][0]["recorded_by"] == "pm-001"
    payload["expected_revision"] = 2
    payload["reason_reviews"][0].update(
        status="confirmed",
        confirmed_reason="事实",
        evidence="证据",
        fact_confirmed_by="张三",
        confirmation_source="会议",
    )
    assert write(client, "PATCH", path, payload).status_code == 422
    payload["reason_reviews"][0]["category"] = "其他"
    payload["reason_reviews"][0]["recorded_by"] = "spoofed"
    assert write(client, "PATCH", path, payload).status_code == 422


def test_missing_approval_time_is_not_fabricated(retrospective: Any) -> None:
    client, project = retrospective
    with client.app.state.session_factory() as session:
        for proposal in session.query(ChangeProposal):
            proposal.resolved_at = None
        session.commit()
    report = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    events = [e for e in report["facts"]["timeline"] if e["source"] == "mobile"]
    assert all(e["occurred_at"] is None for e in events)
    assert report["facts"]["milestones"][0]["adjusted_variance_days"] is None


def test_confirmation_holds_sqlite_write_lock_until_snapshot_committed(
    retrospective: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import Event, Thread

    from project_manager_api.services.retrospectives import RetrospectiveService

    client, project = retrospective
    draft = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    path = f"/retrospectives/{draft['id']}"
    assert (
        write(
            client,
            "PATCH",
            path,
            {
                "expected_revision": 1,
                "baseline_confirmed": True,
                "baseline_note": "核对",
                "reason_reviews": [],
                "improvements": [],
            },
        ).status_code
        == 200
    )
    original_facts = RetrospectiveService._facts
    started, finished = Event(), Event()
    errors: list[Exception] = []
    workers: list[Thread] = []

    def concurrent_writer() -> None:
        try:
            with client.app.state.session_factory() as session:
                state = session.query(MilestoneRuntimeState).one()
                state.schedule = window(16)
                state.schedule_revision += 1
                started.set()
                session.commit()
        except Exception as exc:
            errors.append(exc)
        finally:
            finished.set()

    def facts_with_interleaving(self: Any, project_id: Any, baseline: Any) -> Any:
        result = original_facts(self, project_id, baseline)
        worker = Thread(target=concurrent_writer)
        workers.append(worker)
        worker.start()
        assert started.wait(2)
        assert not finished.wait(0.15), (
            "concurrent evidence writer escaped the SQLite transaction lock"
        )
        return result

    monkeypatch.setattr(RetrospectiveService, "_facts", facts_with_interleaving)
    response = write(client, "POST", path + "/confirm", {"expected_revision": 2})
    assert response.status_code == 200, response.text
    for worker in workers:
        worker.join(timeout=3)
    assert finished.is_set() and not errors
    assert response.json()["facts"]["milestones"][0]["latest_plan"] == window(15)
    with client.app.state.session_factory() as session:
        assert session.query(MilestoneRuntimeState).one().schedule == window(16)


def test_active_plan_switch_clears_old_plan_runtime_override(retrospective: Any) -> None:
    import copy

    from project_manager_api.db.models import ProjectChangeSet

    client, project = retrospective
    with client.app.state.session_factory() as session:
        initial = session.query(ProjectVersion).one()
        changed = copy.deepcopy(initial.snapshot)
        changed["plan_versions"].append({"name": "切换计划", "milestones": {"节点": window(20)}})
        changed["active_plan_name"] = "切换计划"
        session.add(
            ProjectVersion(
                project_id=uuid.UUID(project),
                version_number=2,
                template_id="test",
                template_version="1",
                document_version="1",
                content_sha256="f" * 64,
                snapshot=changed,
                created_at=datetime(2026, 6, 4, tzinfo=UTC),
            )
        )
        session.add(
            ProjectChangeSet(
                project_id=uuid.UUID(project),
                base_version_number=1,
                source="admin_web",
                operations=[],
                diff=[
                    {
                        "path": "runtime_state[M01].schedule",
                        "operation": "removed",
                        "before": {"value": window(15), "plan_name": "变更计划1", "revision": 2},
                        "after": None,
                    }
                ],
                reason="活动计划切换",
                status="published",
                submitted_by_actor_id="pm-001",
                published_by_actor_id="pm-001",
                created_at=datetime(2026, 6, 4, tzinfo=UTC),
                resolved_at=datetime(2026, 6, 4, tzinfo=UTC),
            )
        )
        runtime = session.query(MilestoneRuntimeState).one()
        runtime.schedule = None
        runtime.schedule_plan_name = None
        session.query(Project).one().current_version_number = 2
        session.commit()
    report = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    milestone = report["facts"]["milestones"][0]
    assert milestone["latest_plan"] == window(20)
    assert milestone["variance_plan"] == window(20)
    assert milestone["effective_adjustment_count"] == 3
    publication = next(
        e
        for e in report["facts"]["timeline"]
        if e["source"] == "admin_web" and e["kind"] == "schedule"
    )
    assert publication["before"] == window(15)
    assert publication["after"] == window(20)


def test_deleted_and_readded_code_does_not_inherit_runtime_values(retrospective: Any) -> None:
    import copy

    from project_manager_api.db.models import ProjectChangeSet

    client, project = retrospective
    with client.app.state.session_factory() as session:
        initial = session.query(ProjectVersion).one()
        removed = copy.deepcopy(initial.snapshot)
        removed["milestones"] = []
        for plan in removed["plan_versions"]:
            plan["milestones"] = {}
        readded = copy.deepcopy(removed)
        unknown = {"state": "tbd", "start_date": None, "end_date": None}
        readded["milestones"] = [
            {"code": "M01", "name": "重新添加节点", "actual_completion": unknown, "assignments": {}}
        ]
        readded["plan_versions"][1]["milestones"] = {"重新添加节点": window(25)}
        for number, data in [(2, removed), (3, readded)]:
            session.add(
                ProjectVersion(
                    project_id=uuid.UUID(project),
                    version_number=number,
                    template_id="test",
                    template_version="1",
                    document_version="1",
                    content_sha256=str(number) * 64,
                    snapshot=data,
                    created_at=datetime(2026, 6, number + 2, tzinfo=UTC),
                )
            )
            session.add(
                ProjectChangeSet(
                    project_id=uuid.UUID(project),
                    base_version_number=number - 1,
                    source="admin_web",
                    operations=[],
                    diff=[],
                    reason="范围变化",
                    status="published",
                    submitted_by_actor_id="pm-001",
                    published_by_actor_id="pm-001",
                    created_at=datetime(2026, 6, number + 2, tzinfo=UTC),
                    resolved_at=datetime(2026, 6, number + 2, tzinfo=UTC),
                )
            )
        session.query(MilestoneRuntimeState).delete()
        session.query(Project).one().current_version_number = 3
        session.commit()
    report = write(client, "POST", f"/projects/{project}/retrospectives", {}).json()
    milestone = report["facts"]["milestones"][0]
    assert milestone["name"] == "重新添加节点"
    assert milestone["latest_plan"] == window(25)
    assert milestone["actual_completion"]["state"] == "tbd"
    assert milestone["original_variance_days"] is None
    scopes = [e for e in report["facts"]["timeline"] if e["kind"] == "scope"]
    assert len(scopes) == 2
    assert scopes[0]["before"]["name"] == "节点" and scopes[0]["after"] is None
    assert scopes[1]["before"] is None and scopes[1]["after"]["name"] == "重新添加节点"
