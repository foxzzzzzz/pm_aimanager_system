from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_start_backend_script_starts_compose_and_migrates_database() -> None:
    script_path = ROOT / "scripts" / "start-backend.ps1"

    assert script_path.exists()
    script = script_path.read_text(encoding="utf-8")

    start_command = 'Invoke-Compose -Arguments @("up", "-d", "--wait", "--wait-timeout", "120")'
    migration_command = (
        'Invoke-Compose -Arguments @("exec", "-T", "api", "python", "-m", "alembic", '
        '"-c", "/app/apps/api/alembic.ini", "upgrade", "head")'
    )
    assert start_command in script
    assert migration_command in script
    assert script.index(start_command) < script.index(migration_command)


def test_start_backend_script_uses_compose_ports_for_access_urls() -> None:
    script = (ROOT / "scripts" / "start-backend.ps1").read_text(encoding="utf-8")

    assert "$bindings = @(& docker compose port $Service $ContainerPort)" in script
    assert "$binding = $bindings | Select-Object -First 1" in script
    assert 'Get-PublishedPort -Service "api" -ContainerPort 8000' in script
    assert 'Get-PublishedPort -Service "admin-web" -ContainerPort 80' in script
    assert "http://localhost:$apiPort/health" in script
    assert "http://localhost:$adminPort" in script


def test_linux_start_backend_script_matches_the_startup_flow() -> None:
    script_path = ROOT / "scripts" / "start-backend.sh"

    assert script_path.exists()
    script = script_path.read_text(encoding="utf-8")

    assert script.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in script
    start_command = "docker compose up -d --wait --wait-timeout 120"
    migration_command = (
        "docker compose exec -T api python -m alembic "
        "-c /app/apps/api/alembic.ini upgrade head"
    )
    assert start_command in script
    assert migration_command in script
    assert script.index(start_command) < script.index(migration_command)


def test_linux_start_backend_script_uses_compose_ports_for_access_urls() -> None:
    script = (ROOT / "scripts" / "start-backend.sh").read_text(encoding="utf-8")

    assert 'get_published_port "api" 8000' in script
    assert 'get_published_port "admin-web" 80' in script
    assert 'http://localhost:${api_port}/health' in script
    assert 'http://localhost:${admin_port}' in script
