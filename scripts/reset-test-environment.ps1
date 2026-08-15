[CmdletBinding()]
param(
    [switch]$ConfirmTestReset
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Compose {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

if (-not $ConfirmTestReset) {
    throw "This permanently removes this local Compose project's PostgreSQL, Redis, and MinIO data. Re-run with -ConfirmTestReset to continue."
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install or start Docker Desktop first."
}

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".env"))) {
    throw "The .env file is missing. This reset script is only for the local Docker test environment."
}

Push-Location $repoRoot
try {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker is not running. Start Docker Desktop first."
    }

    Write-Warning "Removing local test data: PostgreSQL, Redis, and MinIO volumes."
    Invoke-Compose -Arguments @("down", "--volumes", "--remove-orphans")

    Write-Output "Recreating local test services..."
    Invoke-Compose -Arguments @("up", "-d", "--wait", "--wait-timeout", "120")

    Write-Output "Applying database migrations..."
    Invoke-Compose -Arguments @(
        "exec", "-T", "api", "python", "-m", "alembic", "-c",
        "/app/apps/api/alembic.ini", "upgrade", "head"
    )

    Write-Output "Test environment reset completed."
}
finally {
    Pop-Location
}
