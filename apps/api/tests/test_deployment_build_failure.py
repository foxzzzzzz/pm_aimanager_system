import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_every_python_install_uses_the_configured_mirror_and_network_limits() -> None:
    dockerfile = (ROOT / "apps/api/Dockerfile").read_text(encoding="utf-8")
    commands = re.findall(r"^RUN pip install[^\n]+", dockerfile.replace("\\\n", " "), re.M)
    assert len(commands) == 2
    for command in commands:
        assert '--index-url "${PYPI_INDEX_URL}"' in command, command
        assert '--timeout "${PIP_DEFAULT_TIMEOUT}"' in command, command
        assert "--retries 10" in command, command


def _run_deployment(
    tmp_path: Path,
    *,
    response: str | None = None,
    fail_stage: str = "",
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    if os.name == "nt":
        bash = next(
            (
                str(p)
                for p in [
                    Path("C:/Program Files/Git/bin/bash.exe"),
                    Path("D:/Program Files/Git/bin/bash.exe"),
                ]
                if p.is_file()
            ),
            None,
        )
    else:
        bash = shutil.which("bash")
    if bash is None:
        pytest.skip("Bash is required for the executable deployment regression")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    deploy = scripts / "deploy-production.sh"
    shutil.copyfile(ROOT / "scripts/deploy-production.sh", deploy)
    (tmp_path / ".env.production").write_text(
        "API_PUBLIC_DOMAIN=api.example.test\nADMIN_PUBLIC_DOMAIN=admin.example.test\n"
        "ADMIN_API_TOKEN=test-only\n",
        encoding="utf-8",
    )
    trace = tmp_path / "commands.log"
    startup = tmp_path / "fake-commands.sh"
    startup.write_text(
        "docker() {\n"
        '  printf "%s\\n" "$*" >> "$DEPLOY_TEST_LOG"\n'
        '  if [[ -n "$DEPLOY_TEST_FAIL_STAGE" && "$*" == *"$DEPLOY_TEST_FAIL_STAGE"* ]]; then\n'
        "    return 42\n"
        "  fi\n"
        '  if [[ "$*" == *"exec -T api python -c"* ]]; then\n'
        '    while [[ "$1" != "python" ]]; do shift; done\n'
        '    shift; "$DEPLOY_TEST_PYTHON" "$@"\n'
        "  fi\n"
        "}\n"
        "curl() {\n"
        '  if [[ -n "$DEPLOY_TEST_FAIL_STAGE" && "$*" == *"$DEPLOY_TEST_FAIL_STAGE"* ]]; then\n'
        "    return 42\n"
        "  fi\n"
        '  printf "%s\\n" "$DEPLOY_TEST_RESPONSE"\n'
        "}\n",
        encoding="utf-8",
        newline="\n",
    )
    result = subprocess.run(
        [bash, "--noprofile", "--norc", deploy.as_posix()],
        cwd=tmp_path,
        env={
            **os.environ,
            "BASH_ENV": startup.as_posix(),
            "DEPLOY_TEST_LOG": trace.as_posix(),
            "DEPLOY_TEST_FAIL_STAGE": fail_stage,
            "DEPLOY_TEST_PYTHON": Path(sys.executable).as_posix(),
            "DEPLOY_TEST_RESPONSE": response if response is not None else json.dumps(_status()),
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, trace.read_text(encoding="utf-8").splitlines()


def _status(**overrides: object) -> dict[str, object]:
    return {
        "status": "ok",
        "checked_at": "2026-10-26T08:00:00+00:00",
        "notification_failures": 0,
        "stale_pending": 0,
        "unbound_recipients": 0,
        "configuration_issues": [],
        **overrides,
    }


@pytest.mark.parametrize("fail_build", [False, True])
def test_deployment_builds_before_stopping_workers_and_does_not_build_during_switch(
    tmp_path: Path,
    fail_build: bool,
) -> None:
    result, commands = _run_deployment(tmp_path, fail_stage=" build" if fail_build else "")
    build = next((i for i, line in enumerate(commands) if line.endswith(" build")), None)
    assert build is not None, commands
    stops = [i for i, line in enumerate(commands) if " stop " in line]
    starts = [i for i, line in enumerate(commands) if " up " in line]
    if fail_build:
        assert result.returncode == 42, result.stderr
        assert stops == [] and starts == [], commands
    else:
        assert result.returncode == 0, result.stderr
        assert len(stops) == len(starts) == 1, commands
        assert build < stops[0] < starts[0]
        assert commands[stops[0]].endswith("stop notification-beat notification-worker")
        assert "--no-build" in commands[starts[0]]
        assert any("alembic" in line for line in commands[starts[0] + 1 :])


@pytest.mark.parametrize("counts", [(1, 0, 4), (0, 1, 0)])
def test_deployment_reports_operational_alerts_without_failing(
    tmp_path: Path,
    counts: tuple[int, int, int],
) -> None:
    response = json.dumps(
        _status(
            status="alert",
            notification_failures=counts[0],
            stale_pending=counts[1],
            unbound_recipients=counts[2],
        )
    )
    result, _ = _run_deployment(tmp_path, response=response)

    assert result.returncode == 0, result.stderr
    assert response in result.stdout
    assert "warning" in result.stderr.lower()
    assert "Deployment completed." in result.stdout


@pytest.mark.parametrize("status", ["ok", "alert"])
def test_deployment_rejects_production_configuration_issues(tmp_path: Path, status: str) -> None:
    response = json.dumps(_status(status=status, configuration_issues=["missing WeChat AppID"]))
    result, _ = _run_deployment(tmp_path, response=response)

    assert result.returncode != 0
    assert response in result.stdout
    assert "Deployment completed." not in result.stdout


@pytest.mark.parametrize(
    "response",
    [
        "not json",
        "[]",
        "null",
        '{"nested":{"status":"ok"}}',
        json.dumps(_status(status="unknown")),
        json.dumps(_status(configuration_issues=None)),
        json.dumps(_status(configuration_issues="")),
        json.dumps(_status(configuration_issues=[1])),
        json.dumps(_status(notification_failures=True)),
        json.dumps(_status(stale_pending=-1)),
        *[
            json.dumps({key: value for key, value in _status().items() if key != missing})
            for missing in _status()
        ],
    ],
)
def test_deployment_rejects_malformed_or_incomplete_operational_status(
    tmp_path: Path,
    response: str,
) -> None:
    result, _ = _run_deployment(tmp_path, response=response)

    assert result.returncode != 0
    assert "Deployment completed." not in result.stdout


@pytest.mark.parametrize(
    "fail_stage",
    [
        " up ",
        "alembic",
        "/health",
        "/operations/status",
        "exec -T api python -c",
    ],
)
def test_deployment_propagates_service_migration_request_and_parser_failures(
    tmp_path: Path,
    fail_stage: str,
) -> None:
    result, _ = _run_deployment(tmp_path, fail_stage=fail_stage)

    assert result.returncode != 0
    assert "Deployment completed." not in result.stdout
