from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", maxsplit=1)
            values[key] = value
    return values


def test_local_secret_script_generates_and_preserves_required_keys() -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is required to execute the local configuration script")
    script = ROOT / "scripts" / "configure-local-secrets.ps1"
    with TemporaryDirectory(dir=ROOT / "tmp") as directory:
        env_path = Path(directory) / ".env"
        subprocess.run(
            [powershell, "-NoProfile", "-File", script, "-EnvPath", env_path],
            check=True,
            capture_output=True,
            text=True,
        )
        first = _dotenv(env_path)
        subprocess.run(
            [powershell, "-NoProfile", "-File", script, "-EnvPath", env_path],
            check=True,
            capture_output=True,
            text=True,
        )
        second = _dotenv(env_path)

        for key in ("ADMIN_API_TOKEN", "PHONE_HMAC_KEY", "PHONE_ENCRYPTION_KEY"):
            assert len(first[key]) >= 43
            assert second[key] == first[key]
        contents = env_path.read_text(encoding="utf-8-sig")
        assert contents.count("ADMIN_API_TOKEN=") == 1
        assert contents.count("PHONE_HMAC_KEY=") == 1
        assert contents.count("PHONE_ENCRYPTION_KEY=") == 1


def test_local_secret_script_can_rotate_only_the_admin_token() -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is required to execute the local configuration script")
    script = ROOT / "scripts" / "configure-local-secrets.ps1"
    with TemporaryDirectory(dir=ROOT / "tmp") as directory:
        env_path = Path(directory) / ".env"
        subprocess.run(
            [powershell, "-NoProfile", "-File", script, "-EnvPath", env_path],
            check=True,
            capture_output=True,
            text=True,
        )
        before = _dotenv(env_path)
        subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-File",
                script,
                "-EnvPath",
                env_path,
                "-Rotate",
                "-SecretNames",
                "ADMIN_API_TOKEN",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        after = _dotenv(env_path)

        assert after["ADMIN_API_TOKEN"] != before["ADMIN_API_TOKEN"]
        assert after["PHONE_HMAC_KEY"] == before["PHONE_HMAC_KEY"]
        assert after["PHONE_ENCRYPTION_KEY"] == before["PHONE_ENCRYPTION_KEY"]
