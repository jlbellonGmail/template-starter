param(
    [Parameter(Mandatory = $true)]
    [string] $Slug,

    [string] $Branch = "",

    [string] $WorktreeDir = "",

    [ValidateSet("Feature", "Milestone", "Maintenance")]
    [string] $Mode = "Feature",

    [string] $Version = "",

    [int] $PollSeconds = 60,

    [int] $MaxMinutes = 1440,

    [switch] $StartBackground
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "feature-contract.ps1")
$scriptPath = $PSCommandPath

function Test-GitSuccess {
    param([Parameter(Mandatory = $true)][string[]] $Arguments)
    & git @Arguments *> $null
    return ($LASTEXITCODE -eq 0)
}

function Convert-ToPowerShellLiteral {
    param([Parameter(Mandatory = $true)][string] $Value)
    return "'" + ($Value -replace "'", "''") + "'"
}

function Convert-ToStartProcessArgument {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string] $Value)

    # Start-Process recibe una linea de comandos en Windows PowerShell 5.1.
    # Citar todos los argumentos evita que rutas temporales con espacios se
    # separen al crear el proceso hijo.
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Start-LocalReconciler {
    if ([string]::IsNullOrWhiteSpace($Branch)) {
        $versionPrefix = if ([string]::IsNullOrWhiteSpace($Version)) { "" } else { "$Version-" }
        $Branch = if ($Mode -eq "Milestone") { "milestone/$versionPrefix$Slug" } elseif ($Mode -eq "Maintenance") { "maintenance/$versionPrefix$Slug" } else { "feature/$versionPrefix$Slug" }
    }

    $mainRoot = Split-Path -Parent (Get-GitCommonDir)
    if ([string]::IsNullOrWhiteSpace($WorktreeDir)) {
        $WorktreeDir = (Get-Location).Path
    }

    $stateDir = Get-FeatureStateDir
    $safeName = $Slug -replace "[^A-Za-z0-9_.-]", "_"
    $logPath = Join-Path $stateDir "$safeName.log"
    $errorLogPath = Join-Path $stateDir "$safeName.err.log"
    $lockPath = Join-Path $stateDir "$safeName.pid"

    if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
        $existingId = 0
        $rawId = [string](Get-Content -LiteralPath $lockPath -Raw -ErrorAction SilentlyContinue)
        if ([int]::TryParse($rawId.Trim(), [ref] $existingId)) {
            $existing = Get-Process -Id $existingId -ErrorAction SilentlyContinue
            if ($existing -and $existing.ProcessName -match "^(cmd|powershell|pwsh)$") {
                Write-Host "==> Ya existe un reconciliador local para $Slug (PID $existingId). No se inicia otro."
                exit 0
            }
        }
        Remove-Item -LiteralPath $lockPath -Force
    }

    $powershell = (Get-Command powershell.exe -ErrorAction SilentlyContinue)
    if (-not $powershell) {
        $powershell = Get-Command pwsh -ErrorAction Stop
    }

    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $scriptPath,
        "-Slug", $Slug,
        "-Branch", $Branch,
        "-WorktreeDir", $WorktreeDir,
        "-Mode", $Mode,
        "-PollSeconds", $PollSeconds,
        "-MaxMinutes", $MaxMinutes
    )
    if (-not [string]::IsNullOrWhiteSpace($Version)) {
        $arguments += @("-Version", $Version)
    }

    Write-Host "==> Iniciando reconciliador local para $Slug. Log: $logPath"
    try {
        # En sesiones interactivas una ventana oculta permite que el proceso
        # sobreviva al launcher. En Session 0 (runner Windows como servicio)
        # no hay window station disponible y se usa -NoNewWindow.
        $startParams = @{
            FilePath = $powershell.Source
            # Windows PowerShell 5.1 rechaza arrays con valores vacios al
            # bindear Start-Process. El launcher ya calculo todos los
            # parametros; una cadena unica conserva el orden sin nulls.
            ArgumentList = (($arguments | Where-Object { $null -ne $_ -and $_ -ne "" } | ForEach-Object {
                Convert-ToStartProcessArgument ([string]$_)
            }) -join " ")
            WorkingDirectory = $mainRoot
            RedirectStandardOutput = $logPath
            RedirectStandardError = $errorLogPath
            PassThru = $true
        }
        if ([Environment]::UserInteractive) {
            $startParams.WindowStyle = "Hidden"
        }
        else {
            $startParams.NoNewWindow = $true
        }
        $created = Start-Process @startParams

        # Fail-safe: Start-Process puede devolver un objeto de proceso valido
        # (sin lanzar excepcion) aunque el hijo muera de inmediato -- por
        # ejemplo por un fallo de binding de parametros al decodificar
        # -EncodedCommand. No alcanza con "Start-Process no tiro error" para
        # declarar exito: hay que confirmar una senal minima real de arranque
        # (el proceso sigue vivo) antes de escribir el lock y terminar en 0.
        $deadline = (Get-Date).AddSeconds(2)
        $alive = $false
        do {
            if (Get-Process -Id $created.Id -ErrorAction SilentlyContinue) {
                $alive = $true
                break
            }
            Start-Sleep -Milliseconds 100
        } while ((Get-Date) -lt $deadline)

        if (-not $alive) {
            throw "El proceso del reconciliador (PID $($created.Id)) no sigue vivo tras iniciarse; revisar $errorLogPath."
        }

        Set-Content -LiteralPath $lockPath -Value $created.Id -Encoding ASCII
    }
    catch {
        Write-Warning "No pude iniciar el reconciliador local: $($_.Exception.Message)"
        Write-Warning "Esto no bloquea la PR: el cierre remoto lo realiza GitHub Actions y la limpieza local se reconciliara en la proxima ejecucion (o corriendo manualmente 'local-feature-reconcile.ps1 -StartBackground')."
        exit 1
    }
}

if ($StartBackground) {
    Start-LocalReconciler
    exit 0
}

if ([string]::IsNullOrWhiteSpace($Branch)) {
    $versionPrefix = if ([string]::IsNullOrWhiteSpace($Version)) { "" } else { "$Version-" }
    $Branch = if ($Mode -eq "Milestone") { "milestone/$versionPrefix$Slug" } elseif ($Mode -eq "Maintenance") { "maintenance/$versionPrefix$Slug" } else { "feature/$versionPrefix$Slug" }
}

$repoRoot = Get-RepositoryRoot
if ([string]::IsNullOrWhiteSpace($WorktreeDir)) {
    $worktreePrefix = if ([string]::IsNullOrWhiteSpace($Version)) { "" } else { "$Version-" }
    $worktreeName = "$worktreePrefix$Slug"
    $WorktreeDir = Join-Path (Join-Path (Split-Path -Parent $repoRoot) "worktrees") $worktreeName
}

$reconcileItems = if ($Mode -eq "Milestone") {
    @((Read-WorkUnitManifest -Path "runs/milestone-$Slug/work-unit.json").Items)
}
else {
    @($Slug)
}

$stateDir = Get-FeatureStateDir
$safeName = $Slug -replace "[^A-Za-z0-9_.-]", "_"
$lockPath = Join-Path $stateDir "$safeName.pid"

$deadline = (Get-Date).AddMinutes($MaxMinutes)
Write-Host "==> Reconciliador local activo para $Slug. Limpia solo si origin/develop contiene [x] para todos sus items."

try {
    while ((Get-Date) -lt $deadline) {
        Invoke-Checked "git" @("fetch", "origin", "develop", "--prune")
        $remoteRoadmap = (& git show "origin/develop`:ROADMAP.md") -join "`n"
        if ($LASTEXITCODE -ne 0) {
            throw "No pude leer origin/develop:ROADMAP.md."
        }

        $itemStates = @($reconcileItems | ForEach-Object { Get-RoadmapItemState -Content $remoteRoadmap -ItemSlug $_ })
        $allDone = ($itemStates.Count -gt 0) -and (-not ($itemStates | Where-Object { $_.Done -ne 1 -or $_.Ready -ne 0 }))
        $anyAmbiguous = $itemStates | Where-Object { $_.Done -gt 1 -or $_.Ready -gt 1 }

        if ($allDone) {
            Write-Host "==> Cierre remoto detectado para $Slug. Limpiando artefactos locales."
            $mainRoot = Split-Path -Parent (Get-GitCommonDir)
            $worktreeFullPath = [System.IO.Path]::GetFullPath($WorktreeDir)
            $mainRootFullPath = [System.IO.Path]::GetFullPath($mainRoot)
            if ([string]::Equals($worktreeFullPath, $mainRootFullPath, [System.StringComparison]::OrdinalIgnoreCase)) {
                throw "Me niego a remover el checkout principal ($mainRootFullPath) como si fuera un worktree de $Slug."
            }
            Set-Location -LiteralPath $mainRoot
            [Environment]::CurrentDirectory = $mainRoot
            if (Test-Path -LiteralPath $WorktreeDir) {
                try { Invoke-Checked "git" @("worktree", "remove", $WorktreeDir) }
                catch { throw "Cleanup incompleto: worktree Git activo o no removible '$WorktreeDir'. No se fuerza el borrado." }
            }
            Invoke-Checked "git" @("worktree", "prune")
            if (Test-Path -LiteralPath $WorktreeDir) {
                $entries = @(Get-ChildItem -LiteralPath $WorktreeDir -Force -ErrorAction SilentlyContinue)
                if ($entries.Count -gt 0) { throw "Cleanup incompleto: residual físico con archivos: $WorktreeDir" }
                Write-Warning "Residual físico vacío (posible lock Windows): $WorktreeDir"
            }
            if (Test-GitSuccess @("rev-parse", "--verify", "--quiet", $Branch)) {
                Invoke-Checked "git" @("branch", "-d", $Branch)
            }
            # La limpieza cambia worktrees y ramas reales. STATUS se regenera
            # sólo después de ambas operaciones, nunca desde runs históricos.
            $statusScript = Join-Path $PSScriptRoot "update-status.ps1"
            $statusPath = Join-Path $mainRoot "STATUS.md"
            if ((Test-Path -LiteralPath $statusScript -PathType Leaf) -and (Test-Path -LiteralPath $statusPath -PathType Leaf)) {
                $pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue)
                if (-not $pwsh) { $pwsh = Get-Command powershell.exe -ErrorAction Stop }
                & $pwsh.Source -NoProfile -ExecutionPolicy Bypass -File $statusScript -RepositoryRoot $mainRoot
                if ($LASTEXITCODE -ne 0) { throw "Cleanup completado pero no se pudo regenerar STATUS.md." }
            }
            Write-Host "==> Reconciliacion local completa para $Slug."
            exit 0
        }

        if ($anyAmbiguous) {
            throw "Estado remoto ambiguo para $Slug en ROADMAP.md entre sus items: $($reconcileItems -join ', ')."
        }

        Start-Sleep -Seconds $PollSeconds
    }

    throw "Timeout esperando cierre remoto de $Slug en origin/develop."
}
finally {
    if (Test-Path -LiteralPath $lockPath -PathType Leaf) {
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
}
