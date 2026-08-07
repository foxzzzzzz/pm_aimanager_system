param(
    [Parameter(Mandatory = $true)]
    [string]$BackupPath,
    [string]$UtilityImage = "alpine:3.22"
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$allowedRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot "tmp\backups"))
$resolvedBackup = [System.IO.Path]::GetFullPath($BackupPath)
$allowedPrefix = $allowedRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
if ($resolvedBackup -ne $allowedRoot -and -not $resolvedBackup.StartsWith($allowedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "BackupPath must remain inside $allowedRoot"
}

$databaseFile = Join-Path $resolvedBackup "postgres.dump"
$objectFile = Join-Path $resolvedBackup "minio-data.tgz"
$manifestFile = Join-Path $resolvedBackup "manifest.json"
foreach ($path in ($databaseFile, $objectFile, $manifestFile)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing backup artifact: $path" }
}

$manifest = Get-Content -Raw -LiteralPath $manifestFile | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $databaseFile).Hash.ToLowerInvariant() -ne $manifest.database_sha256) {
    throw "PostgreSQL backup checksum mismatch"
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $objectFile).Hash.ToLowerInvariant() -ne $manifest.object_storage_sha256) {
    throw "MinIO backup checksum mismatch"
}

$postgresId = (docker compose ps -q postgres).Trim()
$minioId = (docker compose ps -q minio).Trim()
if (-not $postgresId -or -not $minioId) { throw "PostgreSQL and MinIO containers must be running" }
$databaseUser = (docker compose exec -T postgres printenv POSTGRES_USER).Trim()
if (-not $databaseUser) { throw "POSTGRES_USER is unavailable in the container" }
$uniqueSuffix = [Guid]::NewGuid().ToString("N").Substring(0, 12)
$testDatabase = "project_manager_restore_test_$uniqueSuffix"
$testVolume = "project_manager_restore_test_minio_$uniqueSuffix"

try {
    docker cp $databaseFile "${postgresId}:/tmp/project-manager-restore.dump"
    docker compose exec -T postgres createdb -U $databaseUser $testDatabase
    if ($LASTEXITCODE -ne 0) { throw "Creating disposable restore database failed" }
    docker compose exec -T postgres pg_restore -U $databaseUser -d $testDatabase /tmp/project-manager-restore.dump
    if ($LASTEXITCODE -ne 0) { throw "Restoring PostgreSQL backup failed" }
    $tableCount = docker compose exec -T postgres psql -U $databaseUser -d $testDatabase -Atc "select count(*) from information_schema.tables where table_schema='public';"
    if ([int]$tableCount -lt 1) { throw "Restored database contains no public tables" }

    docker volume create $testVolume | Out-Null
    docker run --rm --mount "type=volume,src=$testVolume,dst=/restore" --mount "type=bind,src=$resolvedBackup,dst=/backup,readonly" $UtilityImage tar -C /restore -xzf /backup/minio-data.tgz
    if ($LASTEXITCODE -ne 0) { throw "MinIO archive restore failed" }
    $restoredObject = docker run --rm --mount "type=volume,src=$testVolume,dst=/restore,readonly" $UtilityImage find /restore -mindepth 1 -print -quit
    if ($LASTEXITCODE -ne 0 -or -not $restoredObject) {
        throw "Restored MinIO volume validation failed"
    }
}
finally {
    docker compose exec -T postgres dropdb -U $databaseUser --if-exists $testDatabase 2>$null
    docker compose exec -T postgres rm -f /tmp/project-manager-restore.dump 2>$null
    docker volume rm -f $testVolume 2>$null | Out-Null
}

Write-Output "Restore drill passed using disposable database $testDatabase."
