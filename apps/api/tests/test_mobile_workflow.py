from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import select

from project_manager_api.api.app import create_app
from project_manager_api.db.base import Base
from project_manager_api.db.models import MemberBinding, MobileUser
from project_manager_api.settings import AppSettings

ROOT = Path(__file__).resolve().parents[3]
WORKBOOK = ROOT / "tests" / "fixtures" / "lyra-template-v1" / "lyra_v1_sanitized.xlsx"
MANIFEST = ROOT / "config" / "templates" / "lyra_project_spec-v1.0.yaml"
PM = {"Authorization": "Bearer test-admin-token"}


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
            admin_api_token="test-admin-token",
            admin_actor_id="pm-001",
            phone_hmac_key="test-phone-key",
            phone_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            wechat_subscription_template_id="test-template",
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
    invitation = response.json()
    assert len(invitation["invitation_token"]) <= 32
    assert invitation["mini_program_path"] == (
        f"pages/index/index?invitation={invitation['invitation_token']}"
    )
    return invitation


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

    with client.app.state.session_factory() as session:
        user = session.scalar(select(MobileUser).where(MobileUser.display_name == "dev:member10"))
        binding = session.scalar(
            select(MemberBinding).where(MemberBinding.project_id == uuid.UUID(project_id))
        )
        assert user is not None and binding is not None
        assert user.phone_masked == "138****0010"
        assert user.phone_hash != "13800000010"
        assert user.phone_ciphertext is not None
        assert "13800000010" not in user.phone_ciphertext
        assert user.phone_key_version == 1
        assert binding.provided_phone_masked == "138****0010"
        assert binding.provided_phone_hash != "13800000010"
        assert "13800000010" not in str(user.__dict__)
        assert "13800000010" not in str(binding.__dict__)


def test_bound_user_can_view_read_only_project_review_without_contacts(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    outsider_headers, _ = _login(client, "dev:review-outsider")
    forbidden = client.get(
        f"/api/v1/mobile/projects/{project_id}/review",
        headers=outsider_headers,
    )
    assert forbidden.status_code == 403

    invitation = _invite(client, project_id, "成员10", "invite-review-member10")
    member_headers, _ = _login(client, "dev:review-member10")
    accepted = client.post(
        "/api/v1/mobile/invitations/accept",
        headers=member_headers,
        json={
            "invitation_token": invitation["invitation_token"],
            "phone_code": "dev:13800000010",
        },
    )
    assert accepted.status_code == 200

    review = client.get(
        f"/api/v1/mobile/projects/{project_id}/review",
        headers=member_headers,
    )

    assert review.status_code == 200
    payload = review.json()
    assert len(payload["product_specs"]) == 70
    assert len(payload["members"]) == 22
    assert len(payload["milestones"]) == 24
    assert payload["milestones"][0]["assignments"].keys() == {"R", "A", "C", "I"}
    assert "phone" not in payload["members"][0]
    assert "email" not in payload["members"][0]


def test_mobile_token_cannot_use_admin_project_data_change_endpoints(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    member_headers, _ = _login(client, "dev:project-data-boundary")

    editable = client.get(
        f"/api/v1/projects/{project_id}/editable-data",
        headers=member_headers,
    )
    assert editable.status_code == 403

    create_change_set = client.post(
        f"/api/v1/projects/{project_id}/change-sets",
        headers={**member_headers, "X-Idempotency-Key": "mobile-admin-boundary"},
        json={
            "base_version_number": 1,
            "source": "mini_program",
            "reason": "尝试越权修改项目基础数据",
            "operations": [
                {
                    "op": "replace",
                    "resource": "product_spec",
                    "key": "OS版本",
                    "value": {"item": "OS版本", "value": "Android 17"},
                }
            ],
        },
    )
    assert create_change_set.status_code == 403


def test_user_can_register_an_explicit_wechat_subscription_grant(
    mobile_workflow: TestClient,
) -> None:
    headers, _ = _login(mobile_workflow, "dev:subscriber")

    first = mobile_workflow.post(
        "/api/v1/mobile/subscription-grants",
        headers=headers,
        json={"template_id": "test-template"},
    )
    second = mobile_workflow.post(
        "/api/v1/mobile/subscription-grants",
        headers=headers,
        json={"template_id": "test-template"},
    )

    assert first.status_code == 200
    assert second.json() == {"template_id": "test-template", "remaining_uses": 2}


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
    assert pending.json()[0]["expected_phone"] == "138****0008"
    assert pending.json()[0]["provided_phone"] == "139****0008"

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


def test_same_mobile_user_cannot_bind_two_member_identities_in_one_project(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    first = _invite(client, project_id, "成员10", "invite-first-identity")
    second = _invite(client, project_id, "成员09", "invite-second-identity")
    headers, _ = _login(client, "dev:duplicate-identity")
    accepted = client.post(
        "/api/v1/mobile/invitations/accept",
        headers=headers,
        json={"invitation_token": first["invitation_token"], "phone": "13800000010"},
    )
    assert accepted.status_code == 200

    duplicate = client.post(
        "/api/v1/mobile/invitations/accept",
        headers=headers,
        json={"invitation_token": second["invitation_token"], "phone": "13800000009"},
    )

    assert duplicate.status_code == 409


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


def test_accountable_member_can_list_only_approvable_pending_proposals(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    responsible = _invite(client, project_id, "成员10", "invite-r-list")
    responsible_headers, _ = _login(client, "dev:r-list")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=responsible_headers,
        json={"invitation_token": responsible["invitation_token"], "phone": "13800000010"},
    )
    proposal = client.post(
        f"/api/v1/mobile/projects/{project_id}/milestones/M23/proposals",
        headers={**responsible_headers, "X-Idempotency-Key": "proposal-for-a-list"},
        json={
            "kind": "delay",
            "base_version_number": 1,
            "start_date": "2026-11-16",
            "end_date": "2026-11-20",
            "reason": "联调延期",
        },
    ).json()
    accountable = _invite(client, project_id, "成员09", "invite-a-list")
    accountable_headers, _ = _login(client, "dev:a-list")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=accountable_headers,
        json={"invitation_token": accountable["invitation_token"], "phone": "13800000009"},
    )

    response = client.get(
        f"/api/v1/mobile/projects/{project_id}/change-proposals",
        headers=accountable_headers,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [proposal["id"]]


def test_only_accountable_member_can_reject_mobile_proposal(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    responsible = _invite(client, project_id, "成员10", "invite-r-reject")
    responsible_headers, _ = _login(client, "dev:r-reject")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=responsible_headers,
        json={"invitation_token": responsible["invitation_token"], "phone": "13800000010"},
    )
    proposal = client.post(
        f"/api/v1/mobile/projects/{project_id}/milestones/M23/proposals",
        headers={**responsible_headers, "X-Idempotency-Key": "proposal-for-a-reject"},
        json={
            "kind": "delay",
            "base_version_number": 1,
            "start_date": "2026-11-16",
            "end_date": "2026-11-20",
            "reason": "联调延期",
        },
    ).json()
    forbidden = client.post(
        f"/api/v1/mobile/change-proposals/{proposal['id']}/reject",
        headers={**responsible_headers, "X-Idempotency-Key": "r-cannot-reject"},
        json={"reason": "执行者不能驳回"},
    )
    assert forbidden.status_code == 403

    accountable = _invite(client, project_id, "成员09", "invite-a-reject")
    accountable_headers, _ = _login(client, "dev:a-reject")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=accountable_headers,
        json={"invitation_token": accountable["invitation_token"], "phone": "13800000009"},
    )
    rejected = client.post(
        f"/api/v1/mobile/change-proposals/{proposal['id']}/reject",
        headers={**accountable_headers, "X-Idempotency-Key": "a-rejects-proposal"},
        json={"reason": "资源未落实，请重新计划"},
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    dashboard = client.get(f"/api/v1/projects/{project_id}/dashboard", headers=PM)
    assert dashboard.json()["current_version_number"] == 1


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
    updated = client.patch(
        f"/api/v1/mobile/issues/{issue.json()['id']}",
        headers={**member_headers, "X-Idempotency-Key": "mobile-issue-update"},
        json={"expected_revision": 1, "status": "处理中"},
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    other_invitation = _invite(client, project_id, "成员11", "invite-other-issue-owner")
    other_headers, _ = _login(client, "dev:other-issue-owner")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=other_headers,
        json={"invitation_token": other_invitation["invitation_token"], "phone": "13800000011"},
    )
    forbidden_delete = client.request(
        "DELETE",
        f"/api/v1/mobile/issues/{issue.json()['id']}",
        headers={**other_headers, "X-Idempotency-Key": "mobile-issue-delete-forbidden"},
        json={"expected_revision": 2, "reason": "越权作废"},
    )
    assert forbidden_delete.status_code == 403
    deleted = client.request(
        "DELETE",
        f"/api/v1/mobile/issues/{issue.json()['id']}",
        headers={**member_headers, "X-Idempotency-Key": "mobile-issue-delete"},
        json={"expected_revision": 2, "reason": "问题已作废"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "已关闭"
    assert deleted.json()["revision"] == 3

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
    message = messages.json()[0]
    marked = client.patch(
        f"/api/v1/mobile/messages/{message['id']}/read",
        headers={**member_headers, "X-Idempotency-Key": "read-binding-message"},
    )
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True


def test_publishing_team_change_revokes_removed_member_access(
    mobile_workflow: TestClient,
) -> None:
    client = mobile_workflow
    project_id = _published_project(client)
    invitation = _invite(client, project_id, "成员10", "invite-revoked-member")
    unused_invitation = _invite(client, project_id, "成员11", "invite-revoked-unused-member")
    member_headers, _ = _login(client, "dev:revoked-member")
    client.post(
        "/api/v1/mobile/invitations/accept",
        headers=member_headers,
        json={"invitation_token": invitation["invitation_token"], "phone": "13800000010"},
    )
    with TemporaryDirectory(dir=ROOT / "tmp") as directory:
        changed = Path(directory) / "team-changed.xlsx"
        shutil.copyfile(WORKBOOK, changed)
        workbook = load_workbook(changed)
        team = workbook["项目团队构成"]
        for row in range(5, 27):
            if team[f"C{row}"].value == "成员10":
                team[f"C{row}"] = "成员23"
            if team[f"C{row}"].value == "成员11":
                team[f"C{row}"] = "成员24"
        workbook.save(changed)
        workbook.close()
        with changed.open("rb") as source:
            imported = client.post(
                f"/api/v1/projects/{project_id}/imports",
                headers=_admin_headers("import-team-change"),
                files={
                    "file": (
                        changed.name,
                        source,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            ).json()
    published = client.post(
        f"/api/v1/imports/{imported['id']}/publish",
        headers=_admin_headers("publish-team-change"),
        json={"expected_project_version": 1},
    )
    assert published.status_code == 200

    assert client.get("/api/v1/mobile/projects", headers=member_headers).json() == []
    dashboard = client.get(
        f"/api/v1/mobile/projects/{project_id}/dashboard", headers=member_headers
    )
    assert dashboard.status_code == 403
    unused_headers, _ = _login(client, "dev:revoked-unused-member")
    revoked_accept = client.post(
        "/api/v1/mobile/invitations/accept",
        headers=unused_headers,
        json={
            "invitation_token": unused_invitation["invitation_token"],
            "phone": "13800000011",
        },
    )
    assert revoked_accept.status_code == 404


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
