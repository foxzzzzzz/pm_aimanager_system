$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $repoRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        throw "Creating the Python virtual environment failed with exit code $LASTEXITCODE."
    }
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Upgrading pip failed with exit code $LASTEXITCODE."
}
& $venvPython -m pip install -r "$repoRoot\apps\api\requirements.lock"
if ($LASTEXITCODE -ne 0) {
    throw "Installing API dependencies failed with exit code $LASTEXITCODE."
}
& $venvPython -m pip install --no-deps -e "$repoRoot\apps\api"
if ($LASTEXITCODE -ne 0) {
    throw "Installing the editable API package failed with exit code $LASTEXITCODE."
}
pnpm --dir $repoRoot install --frozen-lockfile
if ($LASTEXITCODE -ne 0) {
    throw "Installing workspace dependencies failed with exit code $LASTEXITCODE."
}

Write-Output "Project dependencies are installed."
