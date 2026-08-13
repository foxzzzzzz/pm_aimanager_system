$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$pytestTemp = Join-Path $repoRoot "tmp\pytest"

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Missing .venv. Run .\scripts\bootstrap.ps1 first."
}

Push-Location $repoRoot
try {
    New-Item -ItemType Directory -Force -Path $pytestTemp | Out-Null
    & $venvPython -m ruff check apps/api/migrations apps/api/src apps/api/tests
    if ($LASTEXITCODE -ne 0) { throw "Python lint failed with exit code $LASTEXITCODE." }
    & $venvPython -m mypy apps/api/src
    if ($LASTEXITCODE -ne 0) { throw "Python type checking failed with exit code $LASTEXITCODE." }
    & $venvPython -m pytest apps/api/tests --basetemp $pytestTemp
    if ($LASTEXITCODE -ne 0) { throw "Python tests failed with exit code $LASTEXITCODE." }
    pnpm test
    if ($LASTEXITCODE -ne 0) { throw "JavaScript tests failed with exit code $LASTEXITCODE." }
    pnpm typecheck
    if ($LASTEXITCODE -ne 0) { throw "TypeScript checking failed with exit code $LASTEXITCODE." }
    pnpm build
    if ($LASTEXITCODE -ne 0) { throw "Admin build failed with exit code $LASTEXITCODE." }
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose validation failed with exit code $LASTEXITCODE." }
}
finally {
    Pop-Location
}

Write-Output "All project checks passed."
