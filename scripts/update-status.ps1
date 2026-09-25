param(
    [string]$RepositoryRoot = "",
    [switch]$Json,
    [string]$MachinePath = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "status-lib.ps1")

function Replace-StatusAutoBlock([string]$Content, [string]$Block) {
    $pattern = '(?s)<!-- STATUS:AUTO:BEGIN -->.*?<!-- STATUS:AUTO:END -->'
    $matches = [regex]::Matches($Content, $pattern)
    if ($matches.Count -gt 1) { throw "STATUS.md contiene bloques AUTO duplicados" }
    if ($matches.Count -eq 1) {
        $m = $matches[0]
        return $Content.Substring(0, $m.Index) + $Block + $Content.Substring($m.Index + $m.Length)
    }
    return $Content.TrimEnd([char]13, [char]10) + [Environment]::NewLine + [Environment]::NewLine + $Block + [Environment]::NewLine
}

try {
    $root = if ($RepositoryRoot) { [IO.Path]::GetFullPath($RepositoryRoot) } else { Invoke-StatusGit @("rev-parse", "--show-toplevel") }
    $snapshot = Get-StatusSnapshot $root
    $jsonText = $snapshot | ConvertTo-Json -Depth 20
    if ($MachinePath) {
        [IO.File]::WriteAllText([IO.Path]::GetFullPath($MachinePath), $jsonText + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
    }
    if ($Json) { Write-Output $jsonText; exit 0 }

    $status = Join-Path $root "STATUS.md"
    if (-not (Test-Path -LiteralPath $status -PathType Leaf)) { throw "No existe STATUS.md" }
    Push-Location $root
    try {
        $content = [IO.File]::ReadAllText($status, [Text.Encoding]::UTF8)
        $block = New-StatusBlock $snapshot
        [IO.File]::WriteAllText($status, (Replace-StatusAutoBlock $content $block), (New-Object Text.UTF8Encoding($false)))
        # La propia regeneración modifica STATUS.md; no debe convertir un
        # checkout limpio en dirty.
        $final = if (Invoke-StatusGit @("status", "--porcelain", "--", ":(exclude)STATUS.md")) { "dirty" } else { "clean" }
        if ($final -ne $snapshot.workingTree) {
            $updated = [IO.File]::ReadAllText($status, [Text.Encoding]::UTF8)
            $updated = $updated -replace "- Working tree: $([regex]::Escape($snapshot.workingTree))", "- Working tree: $final"
            [IO.File]::WriteAllText($status, $updated, (New-Object Text.UTF8Encoding($false)))
        }
    } finally { Pop-Location }
    Write-Host "PASS STATUS.md actualizado"
    exit 0
} catch {
    Write-Host ("ERROR " + $_.Exception.Message)
    exit 2
}
