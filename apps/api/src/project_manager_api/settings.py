from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class AppSettings(BaseModel):
    database_url: str
    manifest_paths: list[Path]
    import_storage_path: Path
    max_import_size_bytes: int
    storage_backend: Literal["local", "s3"] = "local"
    object_storage_endpoint: str | None = None
    object_storage_bucket: str | None = None
    object_storage_region: str = "us-east-1"
    object_storage_access_key: str | None = None
    object_storage_secret_key: str | None = None
    allow_development_wechat_login: bool = False
    wechat_app_id: str | None = None
    wechat_app_secret: str | None = None
    mobile_session_days: int = 30
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "provider-model-name"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2
    llm_structured_output_mode: Literal["auto", "strict", "json"] = "auto"
    admin_api_token: str | None = None
    admin_actor_id: str = "pm-001"
    phone_hmac_key: str | None = None
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:15173"])

    @classmethod
    def from_environment(cls) -> AppSettings:
        config_path = Path(
            os.environ.get("APP_CONFIG_PATH", REPOSITORY_ROOT / "config" / "app.example.yaml")
        )
        config = _load_yaml(config_path)
        database_url = os.environ.get(
            "PROJECT_MANAGER_DATABASE_URL", str(config["database"]["url"])
        )
        manifest_paths = [
            _resolve_path(config_path, Path(value)) for value in config["imports"]["manifest_paths"]
        ]
        storage_path = Path(
            os.environ.get(
                "PROJECT_MANAGER_IMPORT_STORAGE_PATH",
                REPOSITORY_ROOT / "tmp" / "imports",
            )
        )
        max_size = int(config["imports"]["max_file_size_mb"]) * 1024 * 1024
        object_storage = config["object_storage"]
        wechat = config["wechat"]
        llm = config["llm"]
        security = config["security"]
        return cls(
            database_url=database_url,
            manifest_paths=manifest_paths,
            import_storage_path=storage_path,
            max_import_size_bytes=max_size,
            storage_backend=os.environ.get(
                "PROJECT_MANAGER_STORAGE_BACKEND", object_storage["backend"]
            ),
            object_storage_endpoint=os.environ.get(
                "PROJECT_MANAGER_S3_ENDPOINT", object_storage["endpoint"]
            ),
            object_storage_bucket=os.environ.get(
                "PROJECT_MANAGER_S3_BUCKET", object_storage["bucket"]
            ),
            object_storage_region=str(object_storage["region"]),
            object_storage_access_key=os.environ.get("PROJECT_MANAGER_S3_ACCESS_KEY"),
            object_storage_secret_key=os.environ.get("PROJECT_MANAGER_S3_SECRET_KEY"),
            allow_development_wechat_login=os.environ.get(
                "PROJECT_MANAGER_ALLOW_DEV_WECHAT_LOGIN", "false"
            ).lower()
            == "true",
            wechat_app_id=os.environ.get("WECHAT_APP_ID", wechat.get("app_id")),
            wechat_app_secret=os.environ.get("WECHAT_APP_SECRET"),
            mobile_session_days=int(wechat.get("session_days", 30)),
            llm_base_url=os.environ.get("LLM_BASE_URL", str(llm["base_url"])),
            llm_api_key=os.environ.get("LLM_API_KEY"),
            llm_model=os.environ.get("LLM_MODEL", str(llm["model"])),
            llm_timeout_seconds=int(llm["timeout_seconds"]),
            llm_max_retries=int(llm["max_retries"]),
            llm_structured_output_mode=llm["structured_output_mode"],
            admin_api_token=os.environ.get(str(security["admin_api_token_env"])),
            admin_actor_id=str(security["admin_actor_id"]),
            phone_hmac_key=os.environ.get(str(security["phone_hmac_key_env"])),
        )


def _load_yaml(path: Path) -> dict[str, Any]:
    return dict(yaml.safe_load(path.read_text(encoding="utf-8")))


def _resolve_path(config_path: Path, configured_path: Path) -> Path:
    if configured_path.is_absolute():
        return configured_path
    for base in (Path.cwd(), config_path.parent.parent, REPOSITORY_ROOT):
        candidate = (base / configured_path).resolve()
        if candidate.exists():
            return candidate
    return (REPOSITORY_ROOT / configured_path).resolve()
