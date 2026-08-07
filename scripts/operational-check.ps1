param(
    [switch]$AllowConfigurationIssues
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot ".env"
$expectedServices = @(
    "postgres", "redis", "minio", "api", "admin-web", "notification-worker", "notification-beat"
)

Push-Location $repoRoot
try {
    $running = @(docker compose ps --services --status running)
    $missing = @($expectedServices | Where-Object { $_ -notin $running })
    if ($missing.Count -gt 0) { throw "Services not running: $($missing -join ', ')" }

    docker compose exec -T notification-worker celery -A project_manager_api.tasks:celery_app inspect ping --timeout 5 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Notification worker did not answer Celery ping" }

    $tokenLine = Get-Content -LiteralPath $envPath | Where-Object { $_.StartsWith("ADMIN_API_TOKEN=") } | Select-Object -First 1
    if (-not $tokenLine) { throw "ADMIN_API_TOKEN is missing from .env" }
    $token = $tokenLine.Substring("ADMIN_API_TOKEN=".Length)
    $portLine = Get-Content -LiteralPath $envPath | Where-Object { $_.StartsWith("API_HOST_PORT=") } | Select-Object -First 1
    $apiPort = if ($portLine) { $portLine.Substring("API_HOST_PORT=".Length) } else { "18000" }
    $apiBaseUrl = "http://127.0.0.1:$apiPort"
    $headers = @{ Authorization = "Bearer $token" }
    $health = Invoke-RestMethod -Uri "$apiBaseUrl/health" -TimeoutSec 5
    if ($health.status -ne "ok") { throw "API health check failed" }
    $status = Invoke-RestMethod -Uri "$apiBaseUrl/api/v1/operations/status" -Headers $headers -TimeoutSec 10
    $status | ConvertTo-Json -Depth 4
    if ($status.status -ne "ok" -and -not $AllowConfigurationIssues) {
        throw "Operational status requires action"
    }
}
finally {
    Pop-Location
}

Write-Output "Operational check passed."
