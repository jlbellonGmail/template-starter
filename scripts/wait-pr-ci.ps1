[CmdletBinding()]
param(
    [string] $PrRef = "",
    [ValidateRange(1, 7200)][int] $TimeoutSeconds = 900,
    [ValidateRange(1, 300)][int] $IntervalSeconds = 10
)

$ErrorActionPreference = "Stop"

function Get-GitHubCliPath {
    $command = Get-Command gh -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $defaultPath = Join-Path $env:ProgramFiles "GitHub CLI\gh.exe"
    if (Test-Path -LiteralPath $defaultPath -PathType Leaf) { return $defaultPath }
    throw "GitHub CLI (gh) no esta disponible. Instalalo y autenticalo para verificar CI automaticamente."
}

function Invoke-GhChecksWithTimeout {
    param(
        [Parameter(Mandatory = $true)][string] $GhPath,
        [Parameter(Mandatory = $true)][string] $Ref,
        [Parameter(Mandatory = $true)][int] $Timeout,
        [Parameter(Mandatory = $true)][int] $Interval
    )

    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $GhPath
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    foreach ($argument in @("pr", "checks", $Ref, "--watch", "--interval", [string]$Interval)) {
        [void]$psi.ArgumentList.Add($argument)
    }

    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $psi
    try {
        if (-not $process.Start()) { throw "No se pudo iniciar gh para verificar CI." }
        if (-not $process.WaitForExit($Timeout * 1000)) {
            try { $process.Kill($true) } catch { }
            throw "Timeout de CI tras ${Timeout}s para '$Ref'. BLOCKED/TEMPORAL."
        }

        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        if ($process.ExitCode -ne 0) {
            throw "Los checks de CI no terminaron en verde para '$Ref'. $($stderr.Trim()) $($stdout.Trim())"
        }
    }
    finally {
        $process.Dispose()
    }
}

$ghPath = Get-GitHubCliPath
if ([string]::IsNullOrWhiteSpace($PrRef)) {
    $PrRef = ((& git branch --show-current) -join [Environment]::NewLine).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($PrRef)) {
        throw "No pude detectar rama actual para ubicar la PR."
    }
}

Write-Host "==> Esperando checks de CI para PR/rama '$PrRef' (timeout ${TimeoutSeconds}s)..."
Invoke-GhChecksWithTimeout -GhPath $ghPath -Ref $PrRef -Timeout $TimeoutSeconds -Interval $IntervalSeconds
Write-Host "==> CI verde para '$PrRef'."
