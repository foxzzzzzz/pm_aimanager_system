from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from project_manager_api.db.models import NotificationDelivery
from project_manager_api.services.crypto import PhoneCipher
from project_manager_api.settings import AppSettings


def production_configuration_issues(settings: AppSettings) -> list[str]:
    issues: list[str] = []
    if settings.allow_development_wechat_login:
        issues.append("development WeChat login must be disabled")
    if _missing_or_placeholder(settings.wechat_app_id):
        issues.append("a production WeChat AppID is required")
    if _missing_or_placeholder(settings.wechat_app_secret):
        issues.append("a production WeChat AppSecret is required")
    if _missing_or_placeholder(settings.wechat_subscription_template_id):
        issues.append("a production WeChat subscription template is required")
    if not settings.admin_api_token or len(settings.admin_api_token) < 32:
        issues.append("ADMIN_API_TOKEN must contain at least 32 characters")
    if not settings.phone_hmac_key or len(settings.phone_hmac_key) < 32:
        issues.append("PHONE_HMAC_KEY must contain at least 32 characters")
    try:
        PhoneCipher(settings.phone_encryption_key)
    except ValueError:
        issues.append("PHONE_ENCRYPTION_KEY must be a valid 32-byte base64url key")
    if any("localhost" in origin or "127.0.0.1" in origin for origin in settings.cors_origins):
        issues.append("localhost CORS origins are not allowed in production")
    if not settings.sms_enabled:
        issues.append("Tencent SMS fallback must be enabled after channel verification")
    if any(
        _missing_or_placeholder(value)
        for value in (
            settings.tencent_secret_id,
            settings.tencent_secret_key,
            settings.sms_sdk_app_id,
            settings.sms_sign_name,
            settings.sms_critical_template_id,
        )
    ):
        issues.append("Tencent SMS credentials and approved template settings are incomplete")
    return issues


def build_operational_status(
    session: Session,
    settings: AppSettings,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    failure_cutoff = current - timedelta(
        hours=settings.operations_notification_failure_window_hours
    )
    stale_cutoff = current - timedelta(minutes=settings.operations_stale_pending_minutes)
    failures = int(
        session.scalar(
            select(func.count(NotificationDelivery.id)).where(
                NotificationDelivery.channel.in_(("wechat", "sms")),
                NotificationDelivery.status == "failed",
                NotificationDelivery.created_at >= failure_cutoff,
            )
        )
        or 0
    )
    stale_pending = int(
        session.scalar(
            select(func.count(NotificationDelivery.id)).where(
                NotificationDelivery.status == "pending",
                NotificationDelivery.created_at < stale_cutoff,
            )
        )
        or 0
    )
    skipped_unbound = int(
        session.scalar(
            select(func.count(NotificationDelivery.id)).where(
                NotificationDelivery.status == "skipped",
                NotificationDelivery.error_message == "recipient has no bound mobile identity",
                NotificationDelivery.created_at >= failure_cutoff,
            )
        )
        or 0
    )
    config_issues = production_configuration_issues(settings)
    alert = (
        failures >= settings.operations_notification_failure_threshold
        or stale_pending > 0
        or skipped_unbound > 0
        or bool(config_issues)
    )
    return {
        "status": "alert" if alert else "ok",
        "checked_at": current.isoformat(),
        "notification_failures": failures,
        "stale_pending": stale_pending,
        "unbound_recipients": skipped_unbound,
        "configuration_issues": config_issues,
    }


def _missing_or_placeholder(value: str | None) -> bool:
    return not value or value.startswith("replace-with-")
