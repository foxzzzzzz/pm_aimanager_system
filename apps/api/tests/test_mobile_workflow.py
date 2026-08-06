from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from fastapi.testclient import TestClient

from project_manager_api.api.app import create_app
from project_manager_api.db.base import Base
from project_manager_api.settings import AppSettings

ROOT = Path(__file__).resolve().parents[3]
WORKBOOK = ROOT / "tests" / "fixtures" / "lyra-template-v1" / "lyra_v1_sanitized.xlsx"
MANIFEST = ROOT / "config" / "templates" / "lyra_project_spec-v1.0.yaml"
PM = {"X-Actor-Id": "pm-001"}


@pytest.fixture
def mobile_workflow() -> Iterator[TestClient]:
    with TemporaryDirectory(dir=ROOT / "tmp") as directory:
        workdir = Path(directory)
        settings = AppSettings(
            database_url=f"sqlite:///{workdir / 'phase3.sqlite'}",
            manifest_paths=[MANIFEST],
            import_storage_path=workdir / "imports",
            max_import_size_bytes=20 * 1024 * 1024,
            allow_development_wechat_login=True,
        )
        app = create_app(settings)
        Base.metadata.create_all(app.state.engine)
        with TestClient(app) as client:
            yield client
        app.state.engine.dispose()


def _admin_headers(key: str) -> dict[str, str]:
    return {**PM, "X-Idempotency-Key": key}


def _published_project(client: TestClient) -> str:
    project = client.post(
        "/api/v1/projects",
        headers=_admin_headers("phase3-create-project"),
        json={"code": "ZPD1322", "name": "Lyra Pro"},
    ).json()
    with WORKBOOK.open("rb") as source:
        imported = client.post(
            f"/api/v1/projects/{project['id']}/imports",
            headers=_admin_headers("phase3-import"),
            files={
                "file": (
                    WORKBOOK.name,
                    source,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        ).json()
    published = client.post(
        f"/api/v1/imports/{imported['id']}/publish",
        headers=_admin_headers("phase3-publish"),
        json={"expected_project_version": 0},
    )
    assert published.status_code == 200
    return str(project["id"])


def _login(client: TestClient, code: str) -> tuple[dict[str, str], dict[str, Any]]:
    response = client.post(
        "/api/v1/mobile/auth/wechat",
        json={"code": code, "display_name": code},
    )
    assert response.status_code == 200
    payload = response.json()
    return {"Authorization": f"Bearer {payload['access_token']}"}, payload


def _invite(
    client: TestClient,
    project_id: str,
    member_name: str,
    key: str,
    expected_phone: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/projects/{project_id}/member-invitations",
        headers=_admin_headers(key),
        json={"member_name": member_name, "expected_phone": expected_phone},
    )
    assert response.status_code == 201
    return response.json()


def test_unbound_user_cannot_view_project_and_bound_user_can(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    outsider_headers, _ = _login(client, "dev:outsider")

    assert client.get("/api/v1/mobile/projects", headers=outsider_headers).json() == []
    forbidden = client.get(
        f"/api/v1/mobile/projects/{project_id}/dashboard", headers=outsider_headers
    )
    assert forbidden.status_code == 403

    invitation = _invite(client, project_id, "成员10", "invite-member10")
    member_headers, _ = _login(client, "dev:member10")
    accepted = client.post(
        "/api/v1/mobile/invitations/accept",
        headers=member_headers,
        json={
            "invitation_token": invitation["invitation_token"],
            "phone_code": "dev:13800000010",
        },
    )

    assert accepted.status_code == 200
    assert accepted.json()["status"] == "bound"
    projects = client.get("/api/v1/mobile/projects", headers=member_headers)
    assert [project["code"] for project in projects.json()] == ["ZPD1322"]
    dashboard = client.get(
        f"/api/v1/mobile/projects/{project_id}/dashboard", headers=member_headers
    )
    assert dashboard.json()["current_version_number"] == 1
    assert len(dashboard.json()["milestones"]) == 24


def test_phone_mismatch_requires_manager_review(mobile_workflow: TestClient) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    invitation = _invite(
        client,
        project_id,
        "成员08",
        "invite-member08",
        expected_phone="13800000008",
    )
    member_headers, _ = _login(client, "dev:member08")

    accepted = client.post(
        "/api/v1/mobile/invitations/accept",
        headers=member_headers,
        json={"invitation_token": invitation["invitation_token"], "phone": "13900000008"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "pending_review"
    assert client.get("/api/v1/mobile/projects", headers=member_headers).json() == []
    pending = client.get(f"/api/v1/projects/{project_id}/member-bindings", headers=PM)
    assert pending.status_code == 200
    assert pending.json()[0]["member_name"] == "成员08"
    assert pending.json()[0]["status"] == "pending_review"

    approved = client.post(
        f"/api/v1/member-bindings/{accepted.json()['id']}/approve",
        headers=_admin_headers("approve-member08"),
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "bound"
    assert len(client.get("/api/v1/mobile/projects", headers=member_headers).json()) == 1


def test_production_binding_rejects_a_phone_number_supplied_by_the_client(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    invitation = _invite(client, project_id, "成员10", "invite-production-phone")
    member_headers, _ = _login(client, "dev:production-phone")
    client.app.state.settings.allow_development_wechat_login = False

    accepted = client.post(
        "/api/v1/mobile/invitations/accept",
        headers=member_headers,
        json={"invitation_token": invitation["invitation_token"], "phone": "13800000010"},
    )

    assert accepted.status_code == 400
    assert accepted.json()["detail"] == "direct phone input is allowed only in development"


def test_responsible_member_can_submit_own_milestone_but_not_another(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    invitation = _invite(client, project_id, "成员10", "invite-progress-member10")
    member_headers, _ = _login(client, "dev:progress-member10")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=member_headers,
        json={"invitation_token": invitation["invitation_token"], "phone": "13800000010"},
    )

    own = client.post(
        f"/api/v1/mobile/projects/{project_id}/milestones/M23/proposals",
        headers={**member_headers, "X-Idempotency-Key": "mobile-complete-m23"},
        json={
            "kind": "completed",
            "base_version_number": 1,
            "actual_completion_date": "2026-08-06",
            "reason": "软件封板已完成",
        },
    )
    other = client.post(
        f"/api/v1/mobile/projects/{project_id}/milestones/M01/proposals",
        headers={**member_headers, "X-Idempotency-Key": "mobile-complete-m01"},
        json={
            "kind": "completed",
            "base_version_number": 1,
            "actual_completion_date": "2026-08-06",
            "reason": "无权更新的节点",
        },
    )

    assert own.status_code == 201
    assert other.status_code == 403
    accountable_invitation = _invite(client, project_id, "成员09", "invite-accountable-member09")
    accountable_headers, _ = _login(client, "dev:accountable-member09")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=accountable_headers,
        json={
            "invitation_token": accountable_invitation["invitation_token"],
            "phone": "13800000009",
        },
    )
    approved = client.post(
        f"/api/v1/mobile/change-proposals/{own.json()['id']}/approve",
        headers={**accountable_headers, "X-Idempotency-Key": "approve-mobile-m23"},
        json={"expected_project_version": 1},
    )
    assert approved.status_code == 200
    assert approved.json()["version_number"] == 2
    dashboard = client.get(
        f"/api/v1/mobile/projects/{project_id}/dashboard", headers=member_headers
    ).json()
    milestone = next(item for item in dashboard["milestones"] if item["code"] == "M23")
    assert milestone["actual_completion"]["end_date"] == "2026-08-06"


def test_mobile_issue_message_center_and_natural_language_prefill(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    invitation = _invite(client, project_id, "成员10", "invite-mobile-features")
    member_headers, _ = _login(client, "dev:mobile-features")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=member_headers,
        json={"invitation_token": invitation["invitation_token"], "phone": "13800000010"},
    )

    issue = client.post(
        f"/api/v1/mobile/projects/{project_id}/issues",
        headers={**member_headers, "X-Idempotency-Key": "mobile-issue"},
        json={
            "description": "软件封板存在阻塞",
            "impact": "影响PVT",
            "owner_name": "成员10",
            "severity": "high",
            "due_date": "2026-08-20",
        },
    )
    assert issue.status_code == 201

    prefill = client.post(
        "/api/v1/mobile/natural-language/prefill",
        headers=member_headers,
        json={"text": "M23延期到2026-08-30，原因是驱动联调"},
    )
    assert prefill.status_code == 200
    assert prefill.json()["milestone_code"] == "M23"
    assert prefill.json()["end_date"] == "2026-08-30"
    assert prefill.json()["requires_confirmation"] is True

    messages = client.get("/api/v1/mobile/messages", headers=member_headers)
    assert messages.status_code == 200
    assert any(item["type"] == "binding_approved" for item in messages.json())


def test_manager_can_reject_mobile_proposal_without_publishing(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    invitation = _invite(client, project_id, "成员10", "invite-rejected-proposal")
    member_headers, _ = _login(client, "dev:rejected-proposal")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=member_headers,
        json={"invitation_token": invitation["invitation_token"], "phone": "13800000010"},
    )
    proposal = client.post(
        f"/api/v1/mobile/projects/{project_id}/milestones/M23/proposals",
        headers={**member_headers, "X-Idempotency-Key": "rejected-m23"},
        json={
            "kind": "delay",
            "base_version_number": 1,
            "start_date": "2026-08-30",
            "end_date": "2026-09-01",
            "reason": "驱动联调延期",
        },
    ).json()

    pending = client.get(f"/api/v1/projects/{project_id}/change-proposals", headers=PM)
    assert pending.status_code == 200
    assert pending.json()[0]["status"] == "pending"
    rejected = client.post(
        f"/api/v1/change-proposals/{proposal['id']}/reject",
        headers=_admin_headers("reject-m23"),
        json={"reason": "不接受延期，请调整资源"},
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    dashboard = client.get(f"/api/v1/projects/{project_id}/dashboard", headers=PM)
    assert dashboard.json()["current_version_number"] == 1
