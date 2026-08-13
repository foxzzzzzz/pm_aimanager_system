from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_production_compose_exposes_only_the_https_gateway() -> None:
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")

    assert "caddy:" in compose
    assert '"80:80"' in compose
    assert '"443:443"' in compose
    assert "api:\n    ports: !reset []" in compose
    assert "admin-web:\n    ports: !reset []" in compose


def test_production_environment_example_keeps_internal_ports_on_loopback() -> None:
    environment = (ROOT / ".env.production.example").read_text(encoding="utf-8")

    assert "POSTGRES_HOST_PORT=127.0.0.1:15432" in environment
    assert "REDIS_HOST_PORT=127.0.0.1:16379" in environment
    assert "MINIO_API_HOST_PORT=127.0.0.1:19000" in environment
    assert "API_HOST_PORT=127.0.0.1:18000" in environment
    assert "ADMIN_WEB_HOST_PORT=127.0.0.1:15173" in environment
    assert "PROJECT_MANAGER_ALLOW_DEV_WECHAT_LOGIN=false" in environment
    assert "PROJECT_MANAGER_SMS_ENABLED=false" in environment


def test_production_initializer_defaults_to_a_wechat_only_deployment() -> None:
    script = (ROOT / "scripts" / "init-production.sh").read_text(encoding="utf-8")

    for name in (
        "API_PUBLIC_DOMAIN",
        "ADMIN_PUBLIC_DOMAIN",
        "TLS_EMAIL",
        "WECHAT_APP_ID",
        "WECHAT_APP_SECRET",
        "WECHAT_SUBSCRIPTION_TEMPLATE_ID",
    ):
        assert name in script
    assert 'read -r -p "Configure Tencent Cloud SMS now? [y/N]: " configure_sms' in script
    assert 'set_value "PROJECT_MANAGER_SMS_ENABLED" "false"' in script
    assert 'if [[ "${configure_sms}" =~ ^[Yy]$ ]]; then' in script
    assert "openssl rand -base64 32" in script
    assert 'generate_secret_if_missing "POSTGRES_PASSWORD"' in script
    assert 'generate_secret_if_missing "MINIO_ROOT_PASSWORD"' in script
    assert 'chmod 600 "${env_path}"' in script


def test_production_deploy_runs_migrations_and_production_checks() -> None:
    script = (ROOT / "scripts" / "deploy-production.sh").read_text(encoding="utf-8")

    compose_command = (
        "docker compose --env-file .env.production -f docker-compose.yml "
        "-f docker-compose.production.yml"
    )
    assert compose_command in script
    assert "alembic -c /app/apps/api/alembic.ini upgrade head" in script
    assert "https://${API_PUBLIC_DOMAIN}/health" in script
    assert "/api/v1/operations/status" in script
