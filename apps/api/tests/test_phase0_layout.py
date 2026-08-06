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
    assert compose["services"]["redis"]["ports"] == ["${REDIS_HOST_PORT:-16379}:6379"]
    for service in ("postgres", "redis", "minio", "api", "admin-web"):
        assert "healthcheck" in compose["services"][service]
