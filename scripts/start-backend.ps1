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

function Get-PublishedPort {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Service,

        [Parameter(Mandatory = $true)]
        [int]$ContainerPort
    )

    $bindings = @(& docker compose port $Service $ContainerPort)
    if ($LASTEXITCODE -ne 0) {
        throw "Cannot resolve the published port for $Service`:$ContainerPort."
    }
    $binding = $bindings | Select-Object -First 1
    if (-not $binding) {
        throw "No published port was found for $Service`:$ContainerPort."
    }

    $portMatch = [regex]::Match($binding.Trim(), ":(?<port>\d+)$")
    if (-not $portMatch.Success) {
        throw "Unexpected published port value for $Service`: $binding"
    }

    return $portMatch.Groups["port"].Value
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install or start Docker Desktop first."
}

if (-not (Test-Path -LiteralPath (Join-Path $repoRoot ".env"))) {
    throw "The .env file is missing. Copy .env.example to .env and configure local secrets first."
}

Push-Location $repoRoot
try {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker is not running. Start Docker Desktop first."
    }

    Write-Output "Starting backend services..."
    Invoke-Compose -Arguments @("up", "-d", "--wait", "--wait-timeout", "120")

    Write-Output "Applying database migrations..."
    Invoke-Compose -Arguments @("exec", "-T", "api", "python", "-m", "alembic", "-c", "/app/apps/api/alembic.ini", "upgrade", "head")

    $apiPort = Get-PublishedPort -Service "api" -ContainerPort 8000
    $adminPort = Get-PublishedPort -Service "admin-web" -ContainerPort 80

    Write-Output "Backend started successfully."
    Write-Output "API health: http://localhost:$apiPort/health"
    Write-Output "Admin web:  http://localhost:$adminPort"
}
finally {
    Pop-Location
}
