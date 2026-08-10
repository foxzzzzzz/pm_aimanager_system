from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from project_manager_api.db.base import Base
from project_manager_api.db.models import NotificationDelivery
from project_manager_api.services.operations import (
    build_operational_status,
    current_business_date,
    production_configuration_issues,
)
from project_manager_api.settings import AppSettings


def _settings(tmp_path: Path, **overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "database_url": f"sqlite:///{tmp_path / 'operations.sqlite'}",
        "manifest_paths": [],
        "import_storage_path": tmp_path / "imports",
        "max_import_size_bytes": 1024,
        "admin_api_token": "a" * 32,
        "phone_hmac_key": "h" * 32,
        "phone_encryption_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "allow_development_wechat_login": False,
        "wechat_app_id": "wx-production-app",
        "wechat_app_secret": "w" * 32,
        "wechat_subscription_template_id": "production-template",
        "cors_origins": ["https://pm.example.com"],
        "sms_enabled": True,
        "tencent_secret_id": "secret-id",
        "tencent_secret_key": "secret-key",
        "sms_sdk_app_id": "1400000000",
        "sms_sign_name": "approved-sign",
        "sms_critical_template_id": "1234567",
    }
    values.update(overrides)
    return AppSettings.model_validate(values)


def test_production_configuration_rejects_development_and_placeholder_values(
    tmp_path: Path,
) -> None:
    settings = _settings(
        tmp_path,
        allow_development_wechat_login=True,
        wechat_app_id="replace-with-wechat-app-id",
        wechat_subscription_template_id="replace-with-template-id",
        cors_origins=["http://localhost:15173"],
    )

    issues = production_configuration_issues(settings)

    assert "development WeChat login must be disabled" in issues
    assert "a production WeChat AppID is required" in issues
    assert "a production WeChat subscription template is required" in issues
    assert "localhost CORS origins are not allowed in production" in issues


def test_business_date_uses_the_configured_timezone(tmp_path: Path) -> None:
    settings = _settings(tmp_path, app_timezone="Asia/Shanghai")

    result = current_business_date(
        settings,
        now=datetime(2026, 8, 9, 17, 0, tzinfo=UTC),
    )

    assert result == date(2026, 8, 10)


def test_production_configuration_requires_complete_sms_credentials_when_enabled(
    tmp_path: Path,
) -> None:
    settings = _settings(
        tmp_path,
        sms_enabled=True,
        tencent_secret_id=None,
        tencent_secret_key=None,
        sms_sdk_app_id=None,
        sms_sign_name=None,
        sms_critical_template_id=None,
    )

    issues = production_configuration_issues(settings)

    assert "Tencent SMS credentials and approved template settings are incomplete" in issues


def test_production_configuration_requires_sms_fallback_to_be_enabled(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        sms_enabled=False,
        tencent_secret_id="secret-id",
        tencent_secret_key="secret-key",
        sms_sdk_app_id="1400000000",
        sms_sign_name="approved-sign",
        sms_critical_template_id="1234567",
    )

    issues = production_configuration_issues(settings)

    assert "Tencent SMS fallback must be enabled after channel verification" in issues


def test_operational_status_alerts_on_failed_and_stale_deliveries(tmp_path: Path) -> None:
    settings = _settings(
        tmp_path,
        operations_notification_failure_threshold=1,
        operations_stale_pending_minutes=10,
    )
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime(2026, 8, 7, 9, 0, tzinfo=UTC)
    session.add_all(
        [
            _delivery("failed", now - timedelta(minutes=5)),
            _delivery("pending", now - timedelta(minutes=20)),
            _delivery("failed_fallback_sent", now - timedelta(minutes=5)),
        ]
    )
    session.commit()

    result = build_operational_status(session, settings, now=now)

    assert result["status"] == "alert"
    assert result["notification_failures"] == 1
    assert result["stale_pending"] == 1
    session.close()
    engine.dispose()


def test_operational_status_alerts_when_a_recipient_is_not_bound(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    engine = create_engine(settings.database_url)
    Base.metadata.create_all(engine)
    session = Session(engine)
    now = datetime(2026, 8, 7, 9, 0, tzinfo=UTC)
    delivery = _delivery("skipped", now - timedelta(minutes=5))
    delivery.error_message = "recipient has no bound mobile identity"
    session.add(delivery)
    session.commit()

    result = build_operational_status(session, settings, now=now)

    assert result["status"] == "alert"
    assert result["unbound_recipients"] == 1
    session.close()
    engine.dispose()


def _delivery(status: str, created_at: datetime) -> NotificationDelivery:
    return NotificationDelivery(
        project_id=None,
        user_id=None,
        event_type="test",
        object_type="milestone",
        object_id="M01",
        channel="wechat",
        business_date=date(2026, 8, 7),
        idempotency_key=uuid.uuid4().hex,
        status=status,
        payload={},
        created_at=created_at,
        updated_at=created_at,
    )
