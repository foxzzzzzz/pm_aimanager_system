from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
from project_manager_api.services.errors import ConflictError, NotFoundError
from project_manager_api.settings import AppSettings


class WechatSender(Protocol):
    def send(self, openid: str, payload: dict[str, object]) -> None: ...


class SmsSender(Protocol):
    def send(self, phone: str, payload: dict[str, object]) -> None: ...


@dataclass(frozen=True)
class ScanResult:
    created: int
    skipped: int


@dataclass(frozen=True)
class Reminder:
    project: Project
    event_type: str
    object_type: str
    object_id: str
    title: str
    body: str
    recipient_names: tuple[str, ...]
    critical: bool


class NotificationService:
    def __init__(
        self,
        session: Session,
        settings: AppSettings,
        *,
        wechat: WechatSender,
        sms: SmsSender,
    ) -> None:
        self.session = session
        self.settings = settings
        self.wechat = wechat
        self.sms = sms
        self.phone_cipher = (
            PhoneCipher(settings.phone_encryption_key) if settings.phone_encryption_key else None
        )
        self._manager_names_cache: dict[Any, list[str]] = {}
        self._external_sent_counts: dict[Any, int] | None = None
        self._grants: dict[Any, WechatSubscriptionGrant] | None = None

    def scan_daily(self, business_date: date) -> ScanResult:
        if business_date.isoweekday() > 5:
            return ScanResult(created=0, skipped=0)
        reminders: list[Reminder] = []
        project_versions = self._active_project_versions()
        issues_by_project: dict[Any, list[Issue]] = defaultdict(list)
        project_ids = [project.id for project, _version in project_versions]
        if project_ids:
            issue_query = select(Issue).where(Issue.project_id.in_(project_ids))
            for issue in self.session.scalars(issue_query):
                issues_by_project[issue.project_id].append(issue)
        for project, version in project_versions:
            reminders.extend(self._milestone_reminders(project, version.snapshot, business_date))
            reminders.extend(
                self._issue_reminders(project, business_date, issues_by_project[project.id])
            )
        result = self._deliver(reminders, business_date)
        self.session.commit()
        return result

    def scan_weekly(self, business_date: date) -> ScanResult:
        if business_date.isoweekday() != self.settings.notification_weekly_weekday:
            return ScanResult(created=0, skipped=0)
        reminders: list[Reminder] = []
        until = business_date + timedelta(days=self.settings.notification_weekly_days)
        project_versions = self._active_project_versions()
        recipient_names = self._bound_names_by_project(
            [project.id for project, _version in project_versions]
        )
        for project, version in project_versions:
            items = self._scheduled_milestones(version.snapshot)
            upcoming = [
                (milestone, window)
                for milestone, window in items
                if not self._completed(milestone)
                and business_date <= date.fromisoformat(window["end_date"]) <= until
            ]
            if not upcoming:
                continue
            names = tuple(recipient_names.get(project.id, []))
            summary = "; ".join(
                f"{milestone['code']} {milestone['name']} ({window['end_date']})"
                for milestone, window in upcoming
            )
            reminders.append(
                Reminder(
                    project=project,
                    event_type="weekly_summary",
                    object_type="project",
                    object_id=str(project.id),
                    title=f"{project.name} weekly plan",
                    body=summary,
                    recipient_names=names,
                    critical=False,
                )
            )
        result = self._deliver(reminders, business_date)
        self.session.commit()
        return result

    def retry_failed(self, delivery_id: Any) -> dict[str, Any]:
        delivery = self.session.get(NotificationDelivery, delivery_id)
        if delivery is None:
            raise NotFoundError("notification delivery not found")
        if delivery.status != "failed" or delivery.channel not in {"wechat", "sms"}:
            raise ConflictError("only failed external deliveries can be retried")
        user = self.session.get(MobileUser, delivery.user_id)
        if user is None:
            raise NotFoundError("notification recipient no longer exists")
        delivery.attempts += 1
        delivery.error_message = None
        delivery.status = "pending"
        self.session.commit()
        try:
            if delivery.channel == "wechat":
                grant = self.session.scalar(
                    select(WechatSubscriptionGrant).where(
                        WechatSubscriptionGrant.user_id == user.id,
                        WechatSubscriptionGrant.template_id
                        == self.settings.wechat_subscription_template_id,
                        WechatSubscriptionGrant.remaining_uses > 0,
                    )
                )
                if grant is None:
                    raise RuntimeError("WeChat subscription grant is unavailable")
                self.wechat.send(user.openid, delivery.payload)
                grant.remaining_uses -= 1
            else:
                if not user.phone_ciphertext or self.phone_cipher is None:
                    raise RuntimeError("encrypted recipient phone is unavailable")
                self.sms.send(self.phone_cipher.decrypt(user.phone_ciphertext), delivery.payload)
        except Exception as exc:
            delivery.status = "failed"
            delivery.error_message = str(exc)[:2000]
            self.session.commit()
            return self._delivery_result(delivery)
        delivery.status = "sent"
        delivery.sent_at = datetime.now(UTC)
        self.session.commit()
        return self._delivery_result(delivery)

    def _milestone_reminders(
        self, project: Project, snapshot: dict[str, Any], business_date: date
    ) -> list[Reminder]:
        reminders: list[Reminder] = []
        for milestone, window in self._scheduled_milestones(snapshot):
            if self._completed(milestone):
                continue
            due_date = date.fromisoformat(window["end_date"])
            delta = (due_date - business_date).days
            if 1 <= delta <= self.settings.notification_due_soon_days:
                event_type, critical = "milestone_due_soon", False
            elif delta == 0:
                event_type, critical = "milestone_due_today", True
            elif delta < 0:
                event_type, critical = "milestone_overdue", True
            else:
                continue
            assignments = milestone.get("assignments", {})
            names = list(assignments.get("R", []))
            overdue_days = max(0, -delta)
            if overdue_days >= self.settings.notification_escalate_accountable_days:
                names.extend(assignments.get("A", []))
            if overdue_days >= self.settings.notification_escalate_manager_days:
                names.extend(self._manager_names(project.id))
            reminders.append(
                Reminder(
                    project=project,
                    event_type=event_type,
                    object_type="milestone",
                    object_id=str(milestone["code"]),
                    title=f"{project.name}: {milestone['name']}",
                    body=f"Planned completion {due_date.isoformat()}",
                    recipient_names=tuple(dict.fromkeys(names)),
                    critical=critical,
                )
            )
        return reminders

    def _issue_reminders(
        self, project: Project, business_date: date, issues: list[Issue]
    ) -> list[Reminder]:
        reminders: list[Reminder] = []
        closed = {"resolved", "closed", "已解决", "已关闭"}
        for issue in issues:
            if issue.status in closed:
                continue
            delta = (issue.due_date - business_date).days
            if 1 <= delta <= self.settings.notification_due_soon_days:
                event_type = "issue_due_soon"
            elif delta == 0:
                event_type = "issue_due_today"
            elif delta < 0:
                event_type = "issue_overdue"
            else:
                continue
            reminders.append(
                Reminder(
                    project=project,
                    event_type=event_type,
                    object_type="issue",
                    object_id=str(issue.id),
                    title=f"{project.name}: issue reminder",
                    body=f"{issue.description} (due {issue.due_date.isoformat()})",
                    recipient_names=tuple(dict.fromkeys(
                        [issue.owner_name] + (issue.accountable_names if delta <= 0 else [])
                    )),
                    critical=issue.severity == "critical" or delta <= 0,
                )
            )
        return reminders

    def _deliver(self, reminders: list[Reminder], business_date: date) -> ScanResult:
        created = 0
        skipped = 0
        bindings_by_recipient: dict[tuple[Any, str], list[MemberBinding]] = defaultdict(list)
        project_ids = {reminder.project.id for reminder in reminders}
        if project_ids:
            for binding in self.session.scalars(
                select(MemberBinding).where(
                    MemberBinding.project_id.in_(project_ids),
                    MemberBinding.status == BindingStatus.BOUND,
                    MemberBinding.user_id.is_not(None),
                )
            ):
                bindings_by_recipient[(binding.project_id, binding.member_name)].append(binding)
        user_ids = {
            binding.user_id
            for bindings in bindings_by_recipient.values()
            for binding in bindings
            if binding.user_id is not None
        }
        users = {
            user.id: user
            for user in self.session.scalars(select(MobileUser).where(MobileUser.id.in_(user_ids)))
        } if user_ids else {}
        self._prepare_external_state(user_ids, business_date)
        for reminder in reminders:
            bindings = [
                binding
                for name in reminder.recipient_names
                for binding in bindings_by_recipient.get((reminder.project.id, name), [])
            ]
            bound_names = {binding.member_name for binding in bindings}
            for missing_name in set(reminder.recipient_names) - bound_names:
                if self._create_unbound_delivery(
                    reminder, missing_name, business_date
                ):
                    skipped += 1
            for binding in bindings:
                if binding.user_id is None:
                    skipped += 1
                    continue
                user = users.get(binding.user_id)
                if user is None:
                    skipped += 1
                    continue
                delivery = self._create_delivery(reminder, user, business_date, "in_app")
                if delivery is None:
                    skipped += 1
                    continue
                self.session.add(
                    InAppMessage(
                        user_id=user.id,
                        project_id=reminder.project.id,
                        type=reminder.event_type,
                        title=reminder.title,
                        body=reminder.body,
                        notification_id=delivery.id,
                    )
                )
                delivery.status = "sent"
                delivery.attempts = 1
                delivery.sent_at = datetime.now(UTC)
                self.session.commit()
                created += 1
                external_sent = self._try_wechat(reminder, user, business_date)
                if reminder.critical and not external_sent:
                    self._try_sms(reminder, user, business_date)
        return ScanResult(created=created, skipped=skipped)

    def _create_unbound_delivery(
        self, reminder: Reminder, recipient_ref: str, business_date: date
    ) -> bool:
        raw_key = ":".join(
            (
                reminder.event_type,
                reminder.object_type,
                reminder.object_id,
                recipient_ref,
                business_date.isoformat(),
                "in_app",
            )
        )
        key = hashlib.sha256(raw_key.encode()).hexdigest()
        if self.session.scalar(
            select(NotificationDelivery.id).where(NotificationDelivery.idempotency_key == key)
        ):
            return False
        self.session.add(
            NotificationDelivery(
                project_id=reminder.project.id,
                user_id=None,
                event_type=reminder.event_type,
                object_type=reminder.object_type,
                object_id=reminder.object_id,
                channel="in_app",
                business_date=business_date,
                idempotency_key=key,
                status="skipped",
                payload={
                    "title": reminder.title,
                    "body": reminder.body,
                    "recipient_ref": recipient_ref,
                },
                error_message="recipient has no bound mobile identity",
            )
        )
        self.session.commit()
        return True

    def _try_wechat(self, reminder: Reminder, user: MobileUser, business_date: date) -> bool:
        template_id = self.settings.wechat_subscription_template_id
        if not template_id:
            return False
        if self._external_limit_reached(user.id, business_date):
            self._skip_external(reminder, user, business_date, "wechat", "daily limit reached")
            return False
        grant = self._grant_for(user.id, template_id)
        if grant is None:
            self._skip_external(
                reminder, user, business_date, "wechat", "subscription grant is unavailable"
            )
            return False
        delivery = self._create_delivery(reminder, user, business_date, "wechat")
        if delivery is None:
            return False
        delivery.attempts = 1
        self.session.commit()
        try:
            self.wechat.send(user.openid, delivery.payload)
        except Exception as exc:  # adapters normalize provider failures here
            delivery.status = "failed"
            delivery.error_message = str(exc)[:2000]
            self.session.commit()
            return False
        grant.remaining_uses -= 1
        delivery.status = "sent"
        delivery.sent_at = datetime.now(UTC)
        self._record_external_send(user.id)
        self.session.commit()
        return True

    def _try_sms(self, reminder: Reminder, user: MobileUser, business_date: date) -> bool:
        if not self.settings.sms_enabled:
            return False
        if not user.phone_ciphertext or self.phone_cipher is None:
            self._skip_external(
                reminder, user, business_date, "sms", "encrypted recipient phone is unavailable"
            )
            return False
        if self._external_limit_reached(user.id, business_date):
            self._skip_external(reminder, user, business_date, "sms", "daily limit reached")
            return False
        delivery = self._create_delivery(reminder, user, business_date, "sms")
        if delivery is None:
            return False
        delivery.attempts = 1
        self.session.commit()
        try:
            phone = self.phone_cipher.decrypt(user.phone_ciphertext)
            self.sms.send(phone, delivery.payload)
        except Exception as exc:
            delivery.status = "failed"
            delivery.error_message = str(exc)[:2000]
            self.session.commit()
            return False
        delivery.status = "sent"
        delivery.sent_at = datetime.now(UTC)
        self._record_external_send(user.id)
        self.session.commit()
        failed_wechat = self.session.scalar(
            select(NotificationDelivery).where(
                NotificationDelivery.project_id == reminder.project.id,
                NotificationDelivery.user_id == user.id,
                NotificationDelivery.event_type == reminder.event_type,
                NotificationDelivery.object_type == reminder.object_type,
                NotificationDelivery.object_id == reminder.object_id,
                NotificationDelivery.business_date == business_date,
                NotificationDelivery.channel == "wechat",
                NotificationDelivery.status == "failed",
            )
        )
        if failed_wechat is not None:
            failed_wechat.status = "failed_fallback_sent"
            self.session.commit()
        return True

    def _skip_external(
        self,
        reminder: Reminder,
        user: MobileUser,
        business_date: date,
        channel: str,
        reason: str,
    ) -> None:
        delivery = self._create_delivery(reminder, user, business_date, channel)
        if delivery is not None:
            delivery.status = "skipped"
            delivery.error_message = reason
            self.session.commit()

    def _create_delivery(
        self, reminder: Reminder, user: MobileUser, business_date: date, channel: str
    ) -> NotificationDelivery | None:
        raw_key = ":".join(
            (
                reminder.event_type,
                reminder.object_type,
                reminder.object_id,
                str(user.id),
                business_date.isoformat(),
                channel,
            )
        )
        key = hashlib.sha256(raw_key.encode()).hexdigest()
        if self.session.scalar(
            select(NotificationDelivery.id).where(NotificationDelivery.idempotency_key == key)
        ):
            return None
        delivery = NotificationDelivery(
            project_id=reminder.project.id,
            user_id=user.id,
            event_type=reminder.event_type,
            object_type=reminder.object_type,
            object_id=reminder.object_id,
            channel=channel,
            business_date=business_date,
            idempotency_key=key,
            status="pending",
            payload={"title": reminder.title, "body": reminder.body},
        )
        try:
            with self.session.begin_nested():
                self.session.add(delivery)
                self.session.flush()
        except IntegrityError:
            return None
        return delivery

    @staticmethod
    def _delivery_result(delivery: NotificationDelivery) -> dict[str, Any]:
        return {
            "id": str(delivery.id),
            "status": delivery.status,
            "attempts": delivery.attempts,
            "error_message": delivery.error_message,
        }

    def _external_limit_reached(self, user_id: Any, business_date: date) -> bool:
        if self._external_sent_counts is not None:
            return self._external_sent_counts.get(user_id, 0) >= (
                self.settings.notification_daily_external_limit
            )
        count = self.session.scalar(
            select(func.count(NotificationDelivery.id)).where(
                NotificationDelivery.user_id == user_id,
                NotificationDelivery.business_date == business_date,
                NotificationDelivery.channel.in_(("wechat", "sms")),
                NotificationDelivery.status == "sent",
            )
        )
        return int(count or 0) >= self.settings.notification_daily_external_limit

    def _prepare_external_state(self, user_ids: set[Any], business_date: date) -> None:
        self._external_sent_counts = {user_id: 0 for user_id in user_ids}
        if user_ids:
            rows = self.session.execute(
                select(NotificationDelivery.user_id, func.count(NotificationDelivery.id))
                .where(
                    NotificationDelivery.user_id.in_(user_ids),
                    NotificationDelivery.business_date == business_date,
                    NotificationDelivery.channel.in_(("wechat", "sms")),
                    NotificationDelivery.status == "sent",
                )
                .group_by(NotificationDelivery.user_id)
            )
            for user_id, count in rows:
                self._external_sent_counts[user_id] = int(count)
        template_id = self.settings.wechat_subscription_template_id
        self._grants = {}
        if user_ids and template_id:
            self._grants = {
                grant.user_id: grant
                for grant in self.session.scalars(
                    select(WechatSubscriptionGrant).where(
                        WechatSubscriptionGrant.user_id.in_(user_ids),
                        WechatSubscriptionGrant.template_id == template_id,
                    )
                )
            }

    def _record_external_send(self, user_id: Any) -> None:
        if self._external_sent_counts is not None:
            self._external_sent_counts[user_id] = self._external_sent_counts.get(user_id, 0) + 1

    def _grant_for(self, user_id: Any, template_id: str) -> WechatSubscriptionGrant | None:
        if self._grants is not None:
            grant = self._grants.get(user_id)
            return grant if grant is not None and grant.remaining_uses > 0 else None
        return self.session.scalar(
            select(WechatSubscriptionGrant).where(
                WechatSubscriptionGrant.user_id == user_id,
                WechatSubscriptionGrant.template_id == template_id,
                WechatSubscriptionGrant.remaining_uses > 0,
            )
        )

    def _manager_names(self, project_id: Any) -> list[str]:
        if project_id in self._manager_names_cache:
            return self._manager_names_cache[project_id]
        actor_ids = set(
            self.session.scalars(
                select(ProjectMembership.actor_id).where(
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.role == ProjectRole.MANAGER,
                )
            )
        )
        if not actor_ids:
            return []
        names = list(
            self.session.scalars(
                select(MemberBinding.member_name).where(
                    MemberBinding.project_id == project_id,
                    MemberBinding.actor_id.in_(actor_ids),
                    MemberBinding.status == BindingStatus.BOUND,
                )
            )
        )
        bound_actors = set(
            self.session.scalars(
                select(MemberBinding.actor_id).where(
                    MemberBinding.project_id == project_id,
                    MemberBinding.actor_id.in_(actor_ids),
                    MemberBinding.status == BindingStatus.BOUND,
                )
            )
        )
        names.extend(f"manager:{actor_id}" for actor_id in actor_ids - bound_actors)
        self._manager_names_cache[project_id] = names
        return names

    def _active_project_versions(self) -> list[tuple[Project, ProjectVersion]]:
        query = (
            select(Project, ProjectVersion)
            .join(
                ProjectVersion,
                and_(
                    ProjectVersion.project_id == Project.id,
                    ProjectVersion.version_number == Project.current_version_number,
                ),
            )
            .where(Project.status == "active")
        )
        return [(project, version) for project, version in self.session.execute(query)]

    def _bound_names_by_project(self, project_ids: list[Any]) -> dict[Any, list[str]]:
        result: dict[Any, list[str]] = defaultdict(list)
        if not project_ids:
            return result
        for project_id, member_name in self.session.execute(
            select(MemberBinding.project_id, MemberBinding.member_name).where(
                MemberBinding.project_id.in_(project_ids),
                MemberBinding.status == BindingStatus.BOUND,
            )
        ):
            result[project_id].append(member_name)
        return result

    @staticmethod
    def _scheduled_milestones(
        snapshot: dict[str, Any],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        active_name = snapshot.get("active_plan_name")
        plan: dict[str, Any] = next(
            (item for item in snapshot.get("plan_versions", []) if item.get("name") == active_name),
            {"milestones": {}},
        )
        result = []
        for milestone in snapshot.get("milestones", []):
            window = plan.get("milestones", {}).get(milestone.get("name"))
            if window and window.get("state") == "scheduled" and window.get("end_date"):
                result.append((milestone, window))
        return result

    @staticmethod
    def _completed(milestone: dict[str, Any]) -> bool:
        actual = milestone.get("actual_completion")
        return bool(actual and actual.get("end_date"))
