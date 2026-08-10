from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from project_manager_api.db.base import Base
from project_manager_api.db.models import (
    BindingStatus,
    InAppMessage,
    Issue,
    MemberBinding,
    MobileUser,
    NotificationDelivery,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectVersion,
    WechatSubscriptionGrant,
)
from project_manager_api.services.crypto import PhoneCipher
from project_manager_api.services.notifications import NotificationService
from project_manager_api.settings import AppSettings


class FakeWechat:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict[str, object]] = []

    def send(self, openid: str, payload: dict[str, object]) -> None:
        if self.fail:
            raise RuntimeError("wechat unavailable")
        self.sent.append({"openid": openid, **payload})


class FakeSms:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    def send(self, phone: str, payload: dict[str, object]) -> None:
        self.sent.append({"phone": phone, **payload})


class CrashAfterWechatAcceptance:
    def send(self, openid: str, payload: dict[str, object]) -> None:
        del openid, payload
        raise SystemExit("worker terminated after provider acceptance")


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        database_url=f"sqlite:///{tmp_path / 'notifications.sqlite'}",
        manifest_paths=[],
        import_storage_path=tmp_path / "imports",
        max_import_size_bytes=1024,
        admin_api_token="admin",
        phone_hmac_key="phone-hmac",
        phone_encryption_key="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        sms_enabled=True,
        wechat_subscription_template_id="template-1",
    )


@pytest.fixture
def notification_context(tmp_path: Path) -> tuple[Session, AppSettings, dict[str, MobileUser]]:
    settings = _settings(tmp_path)
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session = Session(engine)
    project = Project(code="LYRA", name="Lyra", current_version_number=1)
    session.add(project)
    session.flush()
    snapshot = {
        "active_plan_name": "current",
        "members": [{"name": name} for name in ("Rita", "Alan")],
        "milestones": [
            {
                "code": "M01",
                "name": "Prototype",
                "assignments": {"R": ["Rita"], "A": ["Alan"]},
                "actual_completion": None,
            },
            {
                "code": "M02",
                "name": "Completed",
                "assignments": {"R": ["Rita"], "A": []},
                "actual_completion": {"state": "scheduled", "end_date": "2026-08-01"},
            },
        ],
        "plan_versions": [
            {
                "name": "current",
                "milestones": {
                    "Prototype": {
                        "state": "scheduled",
                        "start_date": "2026-08-08",
                        "end_date": "2026-08-10",
                    },
                    "Completed": {
                        "state": "scheduled",
                        "start_date": "2026-08-01",
                        "end_date": "2026-08-01",
                    },
                },
            }
        ],
    }
    session.add(
        ProjectVersion(
            project_id=project.id,
            version_number=1,
            template_id="test",
            template_version="1",
            document_version="1",
            content_sha256="a" * 64,
            snapshot=snapshot,
        )
    )
    cipher = PhoneCipher(settings.phone_encryption_key)
    users: dict[str, MobileUser] = {}
    for index, name in enumerate(("Rita", "Alan"), start=1):
        user = MobileUser(
            openid=f"openid-{name}",
            display_name=name,
            phone_hash=str(index) * 64,
            phone_masked=f"138****000{index}",
            phone_ciphertext=cipher.encrypt(f"1380000000{index}"),
            phone_key_version=1,
        )
        session.add(user)
        session.flush()
        session.add_all(
            [
                MemberBinding(
                    project_id=project.id,
                    member_name=name,
                    user_id=user.id,
                    actor_id=f"mobile:{user.id}",
                    invitation_token_hash=f"{index}" * 64,
                    status=BindingStatus.BOUND,
                    invitation_expires_at=datetime(2027, 1, 1, tzinfo=UTC),
                ),
                ProjectMembership(
                    project_id=project.id,
                    actor_id=f"mobile:{user.id}",
                    role=ProjectRole.RESPONSIBLE,
                ),
            ]
        )
        users[name] = user
    session.add(
        ProjectMembership(
            project_id=project.id,
            actor_id="pm-001",
            role=ProjectRole.MANAGER,
        )
    )
    session.commit()
    yield session, settings, users
    session.close()
    engine.dispose()


def test_phone_cipher_round_trip_and_tamper_detection() -> None:
    cipher = PhoneCipher("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    encrypted = cipher.encrypt("13800000001")

    assert "13800000001" not in encrypted
    assert cipher.decrypt(encrypted) == "13800000001"
    with pytest.raises(InvalidTag):
        cipher.decrypt(encrypted[:-1] + ("A" if encrypted[-1] != "A" else "B"))


def test_due_soon_is_in_app_only_and_daily_scan_is_idempotent(notification_context) -> None:
    session, settings, users = notification_context
    sms = FakeSms()
    service = NotificationService(session, settings, wechat=FakeWechat(), sms=sms)

    first = service.scan_daily(date(2026, 8, 7))
    second = service.scan_daily(date(2026, 8, 7))

    assert first.created == 1
    assert second.created == 0
    message = session.scalar(select(InAppMessage).where(InAppMessage.user_id == users["Rita"].id))
    assert message is not None and message.type == "milestone_due_soon"
    assert sms.sent == []


def test_due_today_falls_back_to_sms_without_subscription(notification_context) -> None:
    session, settings, _ = notification_context
    sms = FakeSms()

    result = NotificationService(session, settings, wechat=FakeWechat(), sms=sms).scan_daily(
        date(2026, 8, 10)
    )

    assert result.created == 1
    assert [item["phone"] for item in sms.sent] == ["13800000001"]
    channels = set(session.scalars(select(NotificationDelivery.channel)))
    assert channels == {"in_app", "wechat", "sms"}


def test_overdue_day_two_escalates_to_accountable(notification_context) -> None:
    session, settings, users = notification_context

    result = NotificationService(
        session, settings, wechat=FakeWechat(), sms=FakeSms()
    ).scan_daily(date(2026, 8, 12))

    assert result.created == 2
    recipients = set(session.scalars(select(InAppMessage.user_id)))
    assert recipients == {users["Rita"].id, users["Alan"].id}


def test_overdue_day_five_records_unbound_manager_escalation(notification_context) -> None:
    session, settings, _ = notification_context

    result = NotificationService(
        session, settings, wechat=FakeWechat(), sms=FakeSms()
    ).scan_daily(date(2026, 8, 17))

    diagnostic = session.scalar(
        select(NotificationDelivery).where(NotificationDelivery.status == "skipped")
    )
    assert result.skipped == 1
    assert diagnostic is not None
    assert diagnostic.payload["recipient_ref"] == "manager:pm-001"


def test_wechat_failure_is_recorded_and_critical_alert_falls_back_to_sms(
    notification_context,
) -> None:
    session, settings, users = notification_context
    session.add(
        WechatSubscriptionGrant(
            user_id=users["Rita"].id,
            template_id="template-1",
            remaining_uses=1,
        )
    )
    session.commit()
    sms = FakeSms()

    NotificationService(session, settings, wechat=FakeWechat(fail=True), sms=sms).scan_daily(
        date(2026, 8, 10)
    )

    wechat = session.scalar(
        select(NotificationDelivery).where(NotificationDelivery.channel == "wechat")
    )
    assert wechat is not None and wechat.status == "failed_fallback_sent"
    assert wechat.attempts == 1
    assert len(sms.sent) == 1


def test_external_delivery_is_durable_before_the_provider_call(notification_context) -> None:
    session, settings, users = notification_context
    session.add(
        WechatSubscriptionGrant(
            user_id=users["Rita"].id,
            template_id="template-1",
            remaining_uses=1,
        )
    )
    session.commit()

    with pytest.raises(SystemExit):
        NotificationService(
            session,
            settings,
            wechat=CrashAfterWechatAcceptance(),
            sms=FakeSms(),
        ).scan_daily(date(2026, 8, 10))
    session.rollback()

    delivery = session.scalar(
        select(NotificationDelivery).where(NotificationDelivery.channel == "wechat")
    )
    assert delivery is not None
    assert delivery.status == "pending"


def test_failed_noncritical_wechat_delivery_can_be_retried(notification_context) -> None:
    session, settings, users = notification_context
    session.add(
        WechatSubscriptionGrant(
            user_id=users["Rita"].id,
            template_id="template-1",
            remaining_uses=1,
        )
    )
    session.commit()
    service = NotificationService(session, settings, wechat=FakeWechat(fail=True), sms=FakeSms())
    service.scan_daily(date(2026, 8, 7))
    delivery = session.scalar(
        select(NotificationDelivery).where(NotificationDelivery.channel == "wechat")
    )
    assert delivery is not None and delivery.status == "failed"

    result = NotificationService(
        session, settings, wechat=FakeWechat(), sms=FakeSms()
    ).retry_failed(delivery.id)

    assert result["status"] == "sent"
    assert result["attempts"] == 2


def test_resolved_issue_and_completed_milestone_do_not_generate_reminders(
    notification_context,
) -> None:
    session, settings, _ = notification_context
    project = session.scalar(select(Project))
    assert project is not None
    session.add(
        Issue(
            project_id=project.id,
            description="resolved",
            impact="none",
            owner_name="Rita",
            severity="critical",
            due_date=date(2026, 8, 7),
            status="resolved",
            created_by_actor_id="pm-001",
        )
    )
    session.commit()

    result = NotificationService(
        session, settings, wechat=FakeWechat(), sms=FakeSms()
    ).scan_daily(date(2026, 8, 7))

    assert result.created == 1  # only M01 due-soon; M02 and the issue are closed


def test_weekly_summary_reaches_all_bound_project_members(notification_context) -> None:
    session, settings, users = notification_context

    result = NotificationService(
        session, settings, wechat=FakeWechat(), sms=FakeSms()
    ).scan_weekly(date(2026, 8, 10))

    assert result.created == 2
    recipients = set(
        session.scalars(
            select(InAppMessage.user_id).where(InAppMessage.type == "weekly_summary")
        )
    )
    assert recipients == {users["Rita"].id, users["Alan"].id}
