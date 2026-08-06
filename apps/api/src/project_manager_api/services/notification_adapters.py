from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from project_manager_api.settings import AppSettings


class WechatSubscriptionSender:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def send(self, openid: str, payload: dict[str, object]) -> None:
        if not self.settings.wechat_app_id or not self.settings.wechat_app_secret:
            raise RuntimeError("WeChat subscription delivery is not configured")
        token_request = Request(
            "https://api.weixin.qq.com/cgi-bin/stable_token",
            data=json.dumps(
                {
                    "grant_type": "client_credential",
                    "appid": self.settings.wechat_app_id,
                    "secret": self.settings.wechat_app_secret,
                    "force_refresh": False,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(token_request, timeout=10) as response:
            token_payload = json.load(response)
        token = token_payload.get("access_token")
        if not token:
            raise RuntimeError(f"WeChat token error: {token_payload.get('errcode', 'unknown')}")
        message = {
            "touser": openid,
            "template_id": self.settings.wechat_subscription_template_id,
            "page": "pages/messages/messages",
            "data": {
                self.settings.wechat_subscription_title_field: {
                    "value": str(payload["title"])[:20]
                },
                self.settings.wechat_subscription_body_field: {
                    "value": str(payload["body"])[:20]
                },
            },
        }
        request = Request(
            "https://api.weixin.qq.com/cgi-bin/message/subscribe/send?"
            + urlencode({"access_token": token}),
            data=json.dumps(message, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
        if result.get("errcode") != 0:
            raise RuntimeError(f"WeChat send error: {result.get('errcode', 'unknown')}")


class TencentSmsSender:
    def __init__(self, settings: AppSettings):
        self.settings = settings

    def send(self, phone: str, payload: dict[str, object]) -> None:
        required = (
            self.settings.tencent_secret_id,
            self.settings.tencent_secret_key,
            self.settings.sms_sdk_app_id,
            self.settings.sms_sign_name,
            self.settings.sms_critical_template_id,
        )
        if not all(required):
            raise RuntimeError("Tencent SMS delivery is not configured")
        body = json.dumps(
            {
                "PhoneNumberSet": [f"+86{phone}"],
                "SmsSdkAppId": self.settings.sms_sdk_app_id,
                "SignName": self.settings.sms_sign_name,
                "TemplateId": self.settings.sms_critical_template_id,
                "TemplateParamSet": [str(payload["title"])[:32], str(payload["body"])[:64]],
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )
        now = datetime.now(UTC)
        timestamp = int(now.timestamp())
        date_value = now.strftime("%Y-%m-%d")
        host = "sms.tencentcloudapi.com"
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\n"
        canonical_request = "\n".join(
            ("POST", "/", "", canonical_headers, "content-type;host", _sha256(body))
        )
        scope = f"{date_value}/sms/tc3_request"
        string_to_sign = "\n".join(
            ("TC3-HMAC-SHA256", str(timestamp), scope, _sha256(canonical_request))
        )
        secret = str(self.settings.tencent_secret_key)
        secret_date = hmac.new(
            ("TC3" + secret).encode(), date_value.encode(), hashlib.sha256
        ).digest()
        secret_service = hmac.new(secret_date, b"sms", hashlib.sha256).digest()
        secret_signing = hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()
        signature = hmac.new(secret_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
        authorization = (
            "TC3-HMAC-SHA256 "
            f"Credential={self.settings.tencent_secret_id}/{scope}, "
            f"SignedHeaders=content-type;host, Signature={signature}"
        )
        request = Request(
            f"https://{host}",
            data=body.encode(),
            headers={
                "Authorization": authorization,
                "Content-Type": "application/json; charset=utf-8",
                "Host": host,
                "X-TC-Action": "SendSms",
                "X-TC-Timestamp": str(timestamp),
                "X-TC-Version": "2021-01-11",
                "X-TC-Region": self.settings.sms_region,
            },
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            result = json.load(response)
        error = result.get("Response", {}).get("Error")
        if error:
            raise RuntimeError(f"Tencent SMS error: {error.get('Code', 'unknown')}")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
