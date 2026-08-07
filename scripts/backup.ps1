param(
    [string]$BackupRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "tmp\backups"),
    [string]$UtilityImage = "alpine:3.22"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot "tmp\backups"))
$resolvedRoot = [System.IO.Path]::GetFullPath($BackupRoot)
$allowedPrefix = $allowedRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if ($resolvedRoot -ne $allowedRoot -and -not $resolvedRoot.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupRoot must remain inside $allowedRoot"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
$target = Join-Path $resolvedRoot $stamp
New-Item -ItemType Directory -Path $target -Force | Out-Null
$databaseFile = Join-Path $target "postgres.dump"
$objectFile = Join-Path $target "minio-data.tgz"

$postgresId = (docker compose ps -q postgres).Trim()
$minioId = (docker compose ps -q minio).Trim()
if (-not $postgresId -or -not $minioId) {
    throw "PostgreSQL and MinIO containers must be running"
}
$minioInspect = docker inspect $minioId | ConvertFrom-Json
$minioVolume = ($minioInspect[0].Mounts | Where-Object { $_.Destination -eq "/data" }).Name
if (-not $minioVolume) { throw "MinIO data volume could not be resolved" }

try {
    docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/project-manager.dump'
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL backup failed" }
    docker cp "${postgresId}:/tmp/project-manager.dump" $databaseFile
    if ($LASTEXITCODE -ne 0) { throw "Copying PostgreSQL backup failed" }

    docker run --rm --mount "type=volume,src=$minioVolume,dst=/data,readonly" --mount "type=bind,src=$target,dst=/backup" $UtilityImage tar -C /data -czf /backup/minio-data.tgz .
    if ($LASTEXITCODE -ne 0) { throw "MinIO backup failed" }
}
finally {
    docker compose exec -T postgres rm -f /tmp/project-manager.dump 2>$null
}

$manifest = [ordered]@{
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    database_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $databaseFile).Hash.ToLowerInvariant()
    object_storage_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $objectFile).Hash.ToLowerInvariant()
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $target "manifest.json") -Encoding utf8
Write-Output "Backup completed: $target"
