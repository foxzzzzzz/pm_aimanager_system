import io
import json
from pathlib import Path
from typing import Any
from urllib.request import Request

from project_manager_api.services.notification_adapters import WechatSubscriptionSender
from project_manager_api.settings import AppSettings


def test_wechat_sender_reuses_a_valid_access_token(monkeypatch: Any, tmp_path: Path) -> None:
    token_requests = 0
    message_requests = 0

    def fake_urlopen(request: Request, timeout: int) -> io.BytesIO:
        nonlocal token_requests, message_requests
        del timeout
        if request.full_url.endswith("/stable_token"):
            token_requests += 1
            return io.BytesIO(json.dumps({"access_token": "token-1", "expires_in": 7200}).encode())
        message_requests += 1
        return io.BytesIO(json.dumps({"errcode": 0}).encode())

    monkeypatch.setattr(
        "project_manager_api.services.notification_adapters.urlopen",
        fake_urlopen,
    )
    settings = AppSettings(
        database_url="sqlite://",
        manifest_paths=[],
        import_storage_path=tmp_path,
        max_import_size_bytes=1024,
        wechat_app_id="wx-app",
        wechat_app_secret="secret",
        wechat_subscription_template_id="template",
    )
    sender = WechatSubscriptionSender(settings)

    sender.send("openid-1", {"title": "one", "body": "first"})
    sender.send("openid-2", {"title": "two", "body": "second"})

    assert token_requests == 1
    assert message_requests == 2
