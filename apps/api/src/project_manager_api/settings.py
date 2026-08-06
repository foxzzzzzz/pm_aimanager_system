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
