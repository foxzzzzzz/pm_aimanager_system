from __future__ import annotations

from celery import Celery  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]
from sqlalchemy.orm import Session

from project_manager_api.db.session import create_database
from project_manager_api.services.notification_adapters import (
    TencentSmsSender,
    WechatSubscriptionSender,
)
from project_manager_api.services.notifications import NotificationService
from project_manager_api.services.operations import current_business_date
from project_manager_api.settings import AppSettings

settings = AppSettings.from_environment()
celery_app = Celery("project-manager", broker=settings.redis_url, backend=settings.redis_url)


def _schedule(value: str) -> tuple[int, int]:
    hour, minute = value.split(":", maxsplit=1)
    return int(hour), int(minute)


daily_hour, daily_minute = _schedule(settings.notification_daily_scan_time)
weekly_hour, weekly_minute = _schedule(settings.notification_weekly_time)
celery_app.conf.update(
    timezone=settings.app_timezone,
    enable_utc=True,
    beat_schedule={
        "daily-notification-scan": {
            "task": "project_manager.notifications.daily",
            "schedule": crontab(hour=daily_hour, minute=daily_minute),
        },
        "weekly-notification-summary": {
            "task": "project_manager.notifications.weekly",
            "schedule": crontab(
                hour=weekly_hour,
                minute=weekly_minute,
                day_of_week=settings.notification_weekly_weekday % 7,
            ),
        },
    },
)


def _service() -> tuple[NotificationService, Session]:
    _engine, session_factory = create_database(settings.database_url)
    session = session_factory()
    return (
        NotificationService(
            session,
            settings,
            wechat=WechatSubscriptionSender(settings),
            sms=TencentSmsSender(settings),
        ),
        session,
    )


@celery_app.task(name="project_manager.notifications.daily")  # type: ignore[untyped-decorator]
def scan_daily() -> dict[str, int]:
    service, session = _service()
    try:
        business_date = current_business_date(settings)
        result = service.scan_daily(business_date)
        return {"created": result.created, "skipped": result.skipped}
    finally:
        session.close()


@celery_app.task(name="project_manager.notifications.weekly")  # type: ignore[untyped-decorator]
def scan_weekly() -> dict[str, int]:
    service, session = _service()
    try:
        business_date = current_business_date(settings)
        result = service.scan_weekly(business_date)
        return {"created": result.created, "skipped": result.skipped}
    finally:
        session.close()
