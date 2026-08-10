from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from urllib.request import Request

from project_manager_api.services import wechat
from project_manager_api.services.wechat import generate_invitation_entries
from project_manager_api.settings import AppSettings


class _Response(BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        database_url=f"sqlite:///{tmp_path / 'wechat.sqlite'}",
        manifest_paths=[],
        import_storage_path=tmp_path,
        max_import_size_bytes=1024,
        wechat_app_id="wx-test-app",
        wechat_app_secret="test-secret",
        wechat_invitation_page="pages/index/index",
        wechat_invitation_env_version="trial",
        mobile_invitation_days=7,
        wechat_invitation_code_width=430,
    )


def test_generates_url_link_and_unlimited_code_for_invitation(monkeypatch, tmp_path: Path) -> None:
    wechat._access_token_cache.clear()
    requests: list[tuple[str, dict[str, object] | None]] = []
    responses = iter(
        [
            json.dumps({"access_token": "access-token"}).encode(),
            json.dumps({"url_link": "https://wxaurl.cn/invite"}).encode(),
            b"\xff\xd8\xffinvitation-code",
        ]
    )

    def fake_urlopen(request: Request, timeout: int) -> _Response:
        payload = json.loads(request.data) if request.data else None
        requests.append((request.full_url, payload))
        assert timeout == 10
        return _Response(next(responses))

    monkeypatch.setattr("project_manager_api.services.wechat.urlopen", fake_urlopen)

    result = generate_invitation_entries("a" * 32, _settings(tmp_path))

    assert result["mini_program_path"] == f"pages/index/index?invitation={'a' * 32}"
    assert result["url_link"] == "https://wxaurl.cn/invite"
    assert result["mini_program_code_data_url"].startswith("data:image/jpeg;base64,")
    assert result["entry_generation_error"] is None
    assert requests[1][1] == {
        "path": "pages/index/index",
        "query": f"invitation={'a' * 32}",
        "is_expire": True,
        "expire_type": 1,
        "expire_interval": 7,
        "env_version": "trial",
    }
    assert requests[2][1] == {
        "scene": "a" * 32,
        "page": "pages/index/index",
        "check_path": False,
        "env_version": "trial",
        "width": 430,
    }


def test_returns_copyable_path_when_wechat_credentials_are_unavailable(tmp_path: Path) -> None:
    settings = _settings(tmp_path).model_copy(update={"wechat_app_secret": None})

    result = generate_invitation_entries("invite-token", settings)

    assert result["mini_program_path"] == "pages/index/index?invitation=invite-token"
    assert result["url_link"] is None
    assert result["mini_program_code_data_url"] is None
    assert result["entry_generation_error"] == "WeChat invitation links are not configured"


def test_rejects_non_image_mini_program_code_responses(monkeypatch, tmp_path: Path) -> None:
    wechat._access_token_cache.clear()
    responses = iter(
        [
            json.dumps({"access_token": "access-token", "expires_in": 7200}).encode(),
            json.dumps({"url_link": "https://wxaurl.cn/invite"}).encode(),
            b"<html>bad gateway</html>",
        ]
    )
    monkeypatch.setattr(
        "project_manager_api.services.wechat.urlopen",
        lambda _request, timeout: _Response(next(responses)),
    )

    result = generate_invitation_entries("a" * 32, _settings(tmp_path))

    assert result["mini_program_code_data_url"] is None
    assert "invalid image" in result["entry_generation_error"]


def test_reuses_access_token_between_invitation_generations(monkeypatch, tmp_path: Path) -> None:
    wechat._access_token_cache.clear()
    responses = iter(
        [
            json.dumps({"access_token": "access-token", "expires_in": 7200}).encode(),
            json.dumps({"url_link": "https://wxaurl.cn/first"}).encode(),
            b"\xff\xd8\xfffirst",
            json.dumps({"url_link": "https://wxaurl.cn/second"}).encode(),
            b"\xff\xd8\xffsecond",
        ]
    )
    calls: list[str] = []

    def fake_urlopen(request: Request, timeout: int) -> _Response:
        calls.append(request.full_url)
        return _Response(next(responses))

    monkeypatch.setattr("project_manager_api.services.wechat.urlopen", fake_urlopen)

    generate_invitation_entries("a" * 32, _settings(tmp_path))
    generate_invitation_entries("b" * 32, _settings(tmp_path))

    assert sum("stable_token" in url for url in calls) == 1
