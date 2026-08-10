from __future__ import annotations

import base64
import json
import threading
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from project_manager_api.services.errors import ServiceError
from project_manager_api.settings import AppSettings

_access_token_cache: dict[tuple[str, str], tuple[str, float]] = {}
_access_token_lock = threading.Lock()


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
    access_token = wechat_access_token(settings)
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


def generate_invitation_entries(token: str, settings: AppSettings) -> dict[str, Any]:
    query = urlencode({"invitation": token})
    path = build_invitation_path(token, settings)
    result: dict[str, Any] = {
        "mini_program_path": path,
        "url_link": None,
        "mini_program_code_data_url": None,
        "entry_generation_error": None,
    }
    if (
        not settings.wechat_app_id
        or settings.wechat_app_id.startswith("replace-with-")
        or not settings.wechat_app_secret
    ):
        result["entry_generation_error"] = "WeChat invitation links are not configured"
        return result

    try:
        access_token = wechat_access_token(settings)
    except (OSError, ValueError, ServiceError) as exc:
        result["entry_generation_error"] = str(exc)
        return result

    errors: list[str] = []
    try:
        url_payload = _post_json(
            "https://api.weixin.qq.com/wxa/generate_urllink?"
            + urlencode({"access_token": access_token}),
            {
                "path": settings.wechat_invitation_page,
                "query": query,
                "is_expire": True,
                "expire_type": 1,
                "expire_interval": settings.mobile_invitation_days,
                "env_version": settings.wechat_invitation_env_version,
            },
        )
        url_link = url_payload.get("url_link")
        if not url_link:
            raise ServiceError(
                f"WeChat URL Link failed with error {url_payload.get('errcode', 'unknown')}"
            )
        result["url_link"] = str(url_link)
    except (OSError, ValueError, ServiceError) as exc:
        errors.append(str(exc))

    try:
        code_bytes = _post_bytes(
            "https://api.weixin.qq.com/wxa/getwxacodeunlimit?"
            + urlencode({"access_token": access_token}),
            {
                "scene": token,
                "page": settings.wechat_invitation_page,
                "check_path": False,
                "env_version": settings.wechat_invitation_env_version,
                "width": settings.wechat_invitation_code_width,
            },
        )
        stripped = code_bytes.lstrip()
        if stripped.startswith(b"{"):
            error_payload = json.loads(stripped)
            raise ServiceError(
                f"WeChat mini-program code failed with error "
                f"{error_payload.get('errcode', 'unknown')}"
            )
        if code_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            image_type = "png"
        elif code_bytes.startswith(b"\xff\xd8\xff"):
            image_type = "jpeg"
        else:
            raise ServiceError("WeChat mini-program code returned an invalid image response")
        result["mini_program_code_data_url"] = (
            f"data:image/{image_type};base64," + base64.b64encode(code_bytes).decode()
        )
    except (OSError, ValueError, ServiceError) as exc:
        errors.append(str(exc))

    result["entry_generation_error"] = "; ".join(errors) or None
    return result


def build_invitation_path(token: str, settings: AppSettings) -> str:
    return f"{settings.wechat_invitation_page}?{urlencode({'invitation': token})}"


def wechat_access_token(settings: AppSettings) -> str:
    cache_key = (settings.wechat_app_id or "", settings.wechat_app_secret or "")
    now = time.monotonic()
    cached = _access_token_cache.get(cache_key)
    if cached is not None and now < cached[1]:
        return cached[0]
    with _access_token_lock:
        now = time.monotonic()
        cached = _access_token_cache.get(cache_key)
        if cached is not None and now < cached[1]:
            return cached[0]
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
        expires_in = max(60, int(token_payload.get("expires_in", 7200)) - 60)
        token = str(access_token)
        _access_token_cache[cache_key] = (token, time.monotonic() + expires_in)
        return token


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response_bytes = _post_bytes(url, payload)
    parsed: dict[str, Any] = json.loads(response_bytes)
    return parsed


def _post_bytes(url: str, payload: dict[str, Any]) -> bytes:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return bytes(response.read())
