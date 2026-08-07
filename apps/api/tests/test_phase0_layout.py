from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_phase0_required_files_exist() -> None:
    required = [
        "apps/api/pyproject.toml",
        "apps/admin-web/package.json",
        "apps/mini-program/project.config.json",
        "config/app.example.yaml",
        "docker-compose.yml",
        "scripts/check.ps1",
        "scripts/configure-local-secrets.ps1",
        "scripts/backup.ps1",
        "scripts/restore-test.ps1",
        "scripts/operational-check.ps1",
        "tests/fixtures/lyra-template-v1/lyra_v1_sanitized.xlsx",
        "tests/fixtures/lyra-template-v1/expected.json",
    ]

    missing = [path for path in required if not (ROOT / path).exists()]
    assert missing == []


def test_docker_build_uses_locked_runtime_dependencies_and_explicit_indexes() -> None:
    api_dockerfile = (ROOT / "apps" / "api" / "Dockerfile").read_text(encoding="utf-8")
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    assert "requirements.runtime.lock" in api_dockerfile
    assert api_dockerfile.index("COPY apps/api/requirements.runtime.lock") < api_dockerfile.index(
        "COPY apps/api /app/apps/api"
    )
    assert "--retries 10" in api_dockerfile
    assert "PYPI_INDEX_URL" in compose["services"]["api"]["build"]["args"]
    assert "NPM_REGISTRY" in compose["services"]["admin-web"]["build"]["args"]
    assert "PROJECT_MANAGER_DATABASE_URL" in compose["services"]["api"]["environment"]
    assert (
        compose["services"]["api"]["environment"]["PROJECT_MANAGER_IMPORT_STORAGE_PATH"]
        == "/app/tmp/imports"
    )
    assert compose["services"]["redis"]["ports"] == ["${REDIS_HOST_PORT:-16379}:6379"]
    for service in ("postgres", "redis", "minio", "api", "admin-web"):
        assert "healthcheck" in compose["services"][service]
    for service in ("notification-worker", "notification-beat"):
        assert "healthcheck" in compose["services"][service]
    required_sms_environment = {
        "PROJECT_MANAGER_SMS_ENABLED",
        "TENCENT_SECRET_ID",
        "TENCENT_SECRET_KEY",
        "TENCENT_SMS_REGION",
        "TENCENT_SMS_SDK_APP_ID",
        "TENCENT_SMS_SIGN_NAME",
        "TENCENT_SMS_CRITICAL_TEMPLATE_ID",
    }
    for service in ("api", "notification-worker"):
        assert required_sms_environment <= compose["services"][service]["environment"].keys()
