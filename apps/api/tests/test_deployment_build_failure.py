import os
import re
import shutil
import subprocess
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


@pytest.mark.parametrize("fail_build", [False, True])
def test_deployment_builds_before_stopping_workers_and_does_not_build_during_switch(
    tmp_path: Path,
    fail_build: bool,
) -> None:
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
        '  if [[ "$*" == *" build" && "$DEPLOY_TEST_FAIL_BUILD" == "1" ]]; then\n'
        "    return 42\n"
        "  fi\n"
        "}\n"
        "curl() { printf '%s\\n' '{\"status\":\"ok\"}'; }\n",
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
            "DEPLOY_TEST_FAIL_BUILD": "1" if fail_build else "0",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    commands = trace.read_text(encoding="utf-8").splitlines()
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
