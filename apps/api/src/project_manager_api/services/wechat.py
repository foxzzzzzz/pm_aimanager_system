from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from project_manager_api.services.errors import ServiceError
from project_manager_api.settings import AppSettings


def exchange_wechat_code(code: str, settings: AppSettings) -> str:
    if settings.allow_development_wechat_login and code.startswith("dev:"):
        return code
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise ServiceError("WeChat login is not configured")
    query = urlencode(
        {
            "appid": settings.wechat_app_id,
            "secret": settings.wechat_app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
    )
    with urlopen(f"https://api.weixin.qq.com/sns/jscode2session?{query}", timeout=10) as response:
        payload = json.load(response)
    openid = payload.get("openid")
    if not openid:
        raise ServiceError(f"WeChat login failed with error {payload.get('errcode', 'unknown')}")
    return str(openid)


def exchange_wechat_phone(phone_code: str, settings: AppSettings) -> str:
    if settings.allow_development_wechat_login and phone_code.startswith("dev:"):
        return phone_code.removeprefix("dev:")
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise ServiceError("WeChat phone binding is not configured")
    token_request = Request(
        "https://api.weixin.qq.com/cgi-bin/stable_token",
        data=json.dumps(
            {
                "grant_type": "client_credential",
                "appid": settings.wechat_app_id,
                "secret": settings.wechat_app_secret,
                "force_refresh": False,
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(token_request, timeout=10) as response:
        token_payload = json.load(response)
    access_token = token_payload.get("access_token")
    if not access_token:
        raise ServiceError(
            f"WeChat access token failed with error {token_payload.get('errcode', 'unknown')}"
        )
    phone_request = Request(
        "https://api.weixin.qq.com/wxa/business/getuserphonenumber?"
        + urlencode({"access_token": access_token}),
        data=json.dumps({"code": phone_code}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(phone_request, timeout=10) as response:
        phone_payload = json.load(response)
    phone = phone_payload.get("phone_info", {}).get("purePhoneNumber")
    if not phone:
        raise ServiceError(
            f"WeChat phone binding failed with error {phone_payload.get('errcode', 'unknown')}"
        )
    return str(phone)
