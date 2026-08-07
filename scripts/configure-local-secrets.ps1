param(
    [string]$EnvPath = (Join-Path (Split-Path -Parent $PSScriptRoot) ".env"),
    [switch]$Rotate,
    [ValidateSet("ADMIN_API_TOKEN", "PHONE_HMAC_KEY", "PHONE_ENCRYPTION_KEY")]
    [string[]]$SecretNames = @("ADMIN_API_TOKEN", "PHONE_HMAC_KEY", "PHONE_ENCRYPTION_KEY")
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$examplePath = Join-Path $repoRoot ".env.example"
$resolvedParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $EnvPath))
if (-not (Test-Path -LiteralPath $resolvedParent -PathType Container)) {
    throw "The target directory does not exist: $resolvedParent"
}
$resolvedEnvPath = Join-Path $resolvedParent (Split-Path -Leaf $EnvPath)

if (Test-Path -LiteralPath $resolvedEnvPath) {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.AddRange([string[]][System.IO.File]::ReadAllLines($resolvedEnvPath))
}
else {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.AddRange([string[]][System.IO.File]::ReadAllLines($examplePath))
}

function New-SecretValue {
    $bytes = [byte[]]::new(32)
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

function Set-SecretValue([string]$Name) {
    $prefix = "$Name="
    $index = -1
    for ($position = 0; $position -lt $lines.Count; $position++) {
        if ($lines[$position].StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            $index = $position
            break
        }
    }
    if ($index -ge 0 -and -not $Rotate -and $lines[$index].Length -gt $prefix.Length) {
        $currentValue = $lines[$index].Substring($prefix.Length)
        if (-not $currentValue.StartsWith("replace-with-", [System.StringComparison]::Ordinal)) {
            return "preserved"
        }
    }
    $entry = "$prefix$(New-SecretValue)"
    if ($index -ge 0) {
        $lines[$index] = $entry
    }
    else {
        $lines.Add($entry)
    }
    return "generated"
}

$results = [ordered]@{}
foreach ($name in $SecretNames) {
    $results[$name] = Set-SecretValue $name
}

$temporaryPath = "$resolvedEnvPath.tmp"
$utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllLines($temporaryPath, $lines, $utf8WithoutBom)
Move-Item -LiteralPath $temporaryPath -Destination $resolvedEnvPath -Force

Write-Output "Local secret configuration completed at $resolvedEnvPath."
foreach ($entry in $results.GetEnumerator()) {
    Write-Output "$($entry.Key): $($entry.Value)"
}
