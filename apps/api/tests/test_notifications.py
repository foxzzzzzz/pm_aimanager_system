from __future__ import annotations

import hashlib
from dataclasses import replace
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
    MilestoneRuntimeState,
    MobileUser,
    NotificationDelivery,
    Project,
    ProjectMembership,
    ProjectRole,
    ProjectVersion,
    WechatSubscriptionGrant,
)
from project_manager_api.services.crypto import PhoneCipher
from project_manager_api.services.notifications import NotificationService, Reminder
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


def test_wechat_deadline_reminder_prioritizes_status_and_opens_the_target(
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
    wechat = FakeWechat()

    NotificationService(session, settings, wechat=wechat, sms=FakeSms()).scan_daily(
        date(2026, 8, 12)
    )

    message = wechat.sent[0]
    assert message["title"] == "LYRA｜M01 Prototype"
    assert message["body"] == "已逾期 2 天｜截止 08-10"
    assert str(message["page"]).startswith(
        "pages/notification-target/notification-target?projectId="
    )
    assert "objectType=milestone" in str(message["page"])
    assert "objectId=M01" in str(message["page"])
    assert "projectCode=LYRA" in str(message["page"])
    assert "projectName=Lyra" in str(message["page"])


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
            accountable_names=["Alan"],
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


def test_issue_due_today_notifies_responsible_and_accountable_without_ci(
    notification_context,
) -> None:
    session, settings, users = notification_context
    project = session.scalar(select(Project))
    assert project is not None
    session.add(
        Issue(
            project_id=project.id,
            description="issue due today",
            impact="delivery",
            owner_name="Rita",
            accountable_names=["Alan"],
            consulted_names=["Other"],
            informed_names=["Other"],
            severity="high",
            due_date=date(2026, 8, 10),
            status="待处理",
            created_by_actor_id="pm-001",
        )
    )
    session.commit()

    NotificationService(session, settings, wechat=FakeWechat(), sms=FakeSms()).scan_daily(
        date(2026, 8, 10)
    )

    recipients = set(
        session.scalars(
            select(InAppMessage.user_id).where(InAppMessage.type == "issue_due_today")
        )
    )
    assert recipients == {users["Rita"].id, users["Alan"].id}


def test_runtime_completion_suppresses_milestone_reminder(notification_context) -> None:
    session, settings, _ = notification_context
    project = session.scalar(select(Project))
    assert project is not None
    session.add(
        MilestoneRuntimeState(
            project_id=project.id,
            milestone_code="M01",
            actual_completion={"state": "scheduled", "end_date": "2026-08-07"},
            completion_revision=1,
        )
    )
    session.commit()

    result = NotificationService(
        session, settings, wechat=FakeWechat(), sms=FakeSms()
    ).scan_daily(date(2026, 8, 7))

    assert result.created == 0


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


@pytest.mark.parametrize("bound", [False, True])
def test_same_milestone_code_in_two_projects_does_not_share_delivery_key(
    notification_context, bound: bool,
) -> None:
    session, settings, users = notification_context
    project = session.scalar(select(Project))
    assert project is not None
    other = Project(code="NEW", name="New numbering")
    session.add(other)
    session.flush()
    reminder = Reminder(project, "milestone_due_today", "milestone", "M09",
                        "M09 EVT装机", "today", ("Rita",), True)
    other_reminder = replace(reminder, project=other, title="M09 驱动bring up")
    service = NotificationService(session, settings, wechat=FakeWechat(), sms=FakeSms())
    today = date(2026, 10, 22)
    if bound:
        assert service._create_delivery(reminder, users["Rita"], today, "in_app") is not None
        assert service._create_delivery(other_reminder, users["Rita"], today, "in_app") is not None
        assert service._create_delivery(reminder, users["Rita"], today, "in_app") is None
    else:
        assert service._create_unbound_delivery(reminder, "Rita", today)
        assert service._create_unbound_delivery(other_reminder, "Rita", today)
        assert not service._create_unbound_delivery(reminder, "Rita", today)


@pytest.mark.parametrize("channel", ["in_app", "wechat", "sms", "unbound"])
def test_legacy_delivery_keys_are_still_deduplicated_without_resending(
    notification_context, channel: str,
) -> None:
    session, settings, users = notification_context
    project = session.scalar(select(Project))
    assert project is not None
    reminder = Reminder(project, "milestone_due_today", "milestone", "M09",
                        "M09 EVT装机", "today", ("Rita",), True)
    user = users["Rita"]
    today = date(2026, 10, 22)
    actual_channel = "in_app" if channel == "unbound" else channel
    recipient = "Rita" if channel == "unbound" else str(user.id)
    raw = ":".join((reminder.event_type, "milestone", "M09", recipient,
                    today.isoformat(), actual_channel))
    session.add(NotificationDelivery(
        project_id=project.id, user_id=None if channel == "unbound" else user.id,
        event_type=reminder.event_type, object_type="milestone", object_id="M09",
        channel=actual_channel, business_date=today, status="sent", payload={},
        idempotency_key=hashlib.sha256(raw.encode()).hexdigest(),
    ))
    session.commit()
    service = NotificationService(session, settings, wechat=FakeWechat(), sms=FakeSms())
    if channel == "unbound":
        assert not service._create_unbound_delivery(reminder, recipient, today)
    else:
        assert service._create_delivery(reminder, user, today, channel) is None
    other = Project(code="HISTORY-OTHER", name="same node in another project")
    session.add(other)
    session.flush()
    other_reminder = replace(reminder, project=other)
    if channel == "unbound":
        assert service._create_unbound_delivery(other_reminder, recipient, today)
    else:
        assert service._create_delivery(other_reminder, user, today, channel) is not None


@pytest.mark.parametrize("status", ["sent", "pending"])
def test_review_daily_scan_does_not_resend_historical_in_app_delivery(
    notification_context, status: str,
) -> None:
    session, settings, users = notification_context
    project = session.scalar(select(Project))
    assert project is not None
    user = users["Rita"]
    today = date(2026, 8, 10)
    raw = ":".join(("milestone_due_today", "milestone", "M01", str(user.id),
                    today.isoformat(), "in_app"))
    old_key = hashlib.sha256(raw.encode()).hexdigest()
    historical = NotificationDelivery(
        project_id=project.id, user_id=user.id, event_type="milestone_due_today",
        object_type="milestone", object_id="M01", channel="in_app", business_date=today,
        status=status, payload={"title": "historical"}, idempotency_key=old_key,
    )
    session.add(historical)
    session.commit()
    wechat, sms = FakeWechat(), FakeSms()
    service = NotificationService(session, settings, wechat=wechat, sms=sms)
    assert service.scan_daily(today).created == 0
    assert service.scan_daily(today).created == 0
    assert session.scalar(select(InAppMessage)) is None
    assert wechat.sent == [] and sms.sent == []
    session.refresh(historical)
    assert historical.idempotency_key == old_key and historical.status == status


def test_review_failed_historical_sms_can_retry_without_rewriting_its_key(
    notification_context,
) -> None:
    session, settings, users = notification_context
    project = session.scalar(select(Project))
    assert project is not None
    user = users["Rita"]
    today = date(2026, 8, 10)
    raw = ":".join(("milestone_due_today", "milestone", "M01", str(user.id),
                    today.isoformat(), "sms"))
    old_key = hashlib.sha256(raw.encode()).hexdigest()
    historical = NotificationDelivery(
        project_id=project.id, user_id=user.id, event_type="milestone_due_today",
        object_type="milestone", object_id="M01", channel="sms", business_date=today,
        status="failed", attempts=1, payload={"title": "historical"}, idempotency_key=old_key,
    )
    session.add(historical)
    session.commit()
    sms = FakeSms()
    service = NotificationService(session, settings, wechat=FakeWechat(), sms=sms)
    assert service.retry_failed(historical.id)["status"] == "sent"
    assert len(sms.sent) == 1
    assert historical.idempotency_key == old_key and historical.attempts == 2


def test_review_concurrent_unbound_delivery_keeps_the_session_usable(
    notification_context, monkeypatch,
) -> None:
    session, settings, _ = notification_context
    project = session.scalar(select(Project))
    assert project is not None
    reminder = Reminder(project, "milestone_due_today", "milestone", "M09",
                        "M09 EVT装机", "today", ("unbound",), True)
    service = NotificationService(session, settings, wechat=FakeWechat(), sms=FakeSms())
    today = date(2026, 10, 22)
    assert service._create_unbound_delivery(reminder, "unbound", today)
    original_scalar = session.scalar

    def stale_lookup(statement):
        # Simulate another scan inserting the same key after our existence check.
        monkeypatch.setattr(session, "scalar", original_scalar)
        return None

    monkeypatch.setattr(session, "scalar", stale_lookup)
    assert not service._create_unbound_delivery(reminder, "unbound", today)
    assert len(list(session.scalars(select(NotificationDelivery)))) == 1
