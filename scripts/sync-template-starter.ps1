param(
    [Parameter(Mandatory = $true)][string]$StarterPath,
    [ValidateSet('Verify','Sync')][string]$Mode = 'Verify'
)
$ErrorActionPreference = 'Stop'

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$templateRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$starterRoot = [IO.Path]::GetFullPath($StarterPath)
$manifestPath = Join-Path $templateRoot 'scripts/template-starter-manifest.json'
if (-not (Test-Path -LiteralPath $starterRoot -PathType Container)) { throw "No existe StarterPath: $starterRoot" }
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schemaVersion -ne 1) { throw "Manifest de starter no soportado: $manifestPath" }
$drift = @()
foreach ($relative in @($manifest.sharedPaths)) {
    $source = Join-Path $templateRoot $relative
    $target = Join-Path $starterRoot $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Falta fuente declarada: $relative" }
    if ($Mode -eq 'Sync') {
        $parent = Split-Path -Parent $target
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Copy-Item -LiteralPath $source -Destination $target -Force
    }
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { $drift += "missing: $relative"; continue }
    if ((Get-Sha256 $source) -ne (Get-Sha256 $target)) { $drift += "different: $relative" }
}
if ($drift.Count) {
    $drift | ForEach-Object { Write-Host "DRIFT $_" }
    if ($Mode -eq 'Verify') { exit 1 }
}
Write-Host "PASS template-starter $Mode ($($manifest.sharedPaths.Count) rutas compartidas)"
exit 0
