param(
    [string] $Slug = "",

    [int] $PrNumber = 0,

    [string] $Branch = "",

    [string] $WorktreeDir = "",

    [ValidateSet("Feature", "Milestone", "Maintenance")]
    [string] $Mode = "Feature",

    [string] $Version = "",

    [switch] $SkipLocalCleanup
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "workunit-lib.ps1")

function Test-GitSuccess {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    & git @Arguments *> $null
    return ($LASTEXITCODE -eq 0)
}

function Assert-CleanWorktree {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Context
    )

    $status = Get-CheckedOutput "git" @("status", "--short")
    if (-not [string]::IsNullOrWhiteSpace($status)) {
        throw "Hay cambios locales incompatibles $Context. No se continua.`n$status"
    }
}

function Get-RoadmapState {
    # Wrapper delgado sobre la version compartida en workunit-lib.ps1.
    param(
        [Parameter(Mandatory = $true)]
        [string] $Content,

        [Parameter(Mandatory = $true)]
        [string] $Slug
    )

    return Get-RoadmapItemState -Content $Content -ItemSlug $Slug
}

function Assert-RoadmapClosedOnce {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Content,

        [Parameter(Mandatory = $true)]
        [string] $Slug,

        [Parameter(Mandatory = $true)]
        [string] $Context
    )

    $state = Get-RoadmapState $Content $Slug
    if ($state.Done -ne 1 -or $state.Ready -ne 0) {
        throw "Validacion fallida ${Context}: ROADMAP.md debe contener exactamente una entrada [x] $Slug y ninguna [-] $Slug. Estado: pending=$($state.Pending), ready=$($state.Ready), done=$($state.Done)."
    }
}

function Assert-RoadmapCanClose {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Content,

        [Parameter(Mandatory = $true)]
        [string] $Slug
    )

    $state = Get-RoadmapState $Content $Slug
    $total = $state.Pending + $state.Ready + $state.Done

    if ($total -eq 0) {
        throw "No existe una entrada exacta para '$Slug' en ROADMAP.md."
    }

    if ($total -gt 1) {
        throw "ROADMAP.md contiene mas de una coincidencia exacta para '$Slug'. Estado: pending=$($state.Pending), ready=$($state.Ready), done=$($state.Done)."
    }

    if ($state.Done -eq 1) {
        return "already-closed"
    }

    if ($state.Ready -eq 1) {
        return "ready"
    }

    throw "'$Slug' existe en ROADMAP.md pero no esta en READY_FOR_PR. El cierre post-merge solo cambia [-] a [x]."
}

function Assert-RoadmapItemsCanClose {
    # Version Milestone (N items) de Assert-RoadmapCanClose: atomica, todo
    # o nada. Un estado mezclado (algunos [x], otros no) es irrecuperable
    # automaticamente -- no deberia ocurrir porque el cierre escribe todos
    # los items en un unico commit, pero se detecta y rechaza por seguridad.
    param(
        [Parameter(Mandatory = $true)]
        [string] $Content,

        [Parameter(Mandatory = $true)]
        [string[]] $Items
    )

    $states = @{}
    foreach ($item in $Items) {
        $state = Get-RoadmapItemState -Content $Content -ItemSlug $item
        $total = $state.Pending + $state.Ready + $state.Done
        if ($total -eq 0) {
            throw "No existe una entrada exacta para '$item' en ROADMAP.md."
        }
        if ($total -gt 1) {
            throw "ROADMAP.md contiene mas de una coincidencia exacta para '$item'. Estado: pending=$($state.Pending), ready=$($state.Ready), done=$($state.Done)."
        }
        $states[$item] = $state
    }

    $doneItems = @($Items | Where-Object { $states[$_].Done -eq 1 })
    $readyItems = @($Items | Where-Object { $states[$_].Ready -eq 1 })
    $pendingItems = @($Items | Where-Object { $states[$_].Pending -eq 1 })

    if ($doneItems.Count -eq $Items.Count) {
        return "already-closed"
    }

    if ($readyItems.Count -eq $Items.Count) {
        return "ready"
    }

    if ($doneItems.Count -gt 0) {
        throw "Estado ambiguo e irrecuperable automaticamente para el milestone: items ya cerrados [x] ($($doneItems -join ', ')) conviven con items que no lo estan (ready: $($readyItems -join ', '); pending: $($pendingItems -join ', ')). Requiere intervencion manual en ROADMAP.md."
    }

    throw "El milestone tiene items que no estan todos en READY_FOR_PR. El cierre post-merge solo cambia [-] a [x] para TODOS los items a la vez. Items: $($Items -join ', ')."
}

function Assert-RoadmapItemsClosedOnce {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Content,

        [Parameter(Mandatory = $true)]
        [string[]] $Items,

        [Parameter(Mandatory = $true)]
        [string] $Context
    )

    foreach ($item in $Items) {
        Assert-RoadmapClosedOnce $Content $item $Context
    }
}

function Test-RoadmapClosedOnce {
    # Version booleana de Assert-RoadmapClosedOnce: no lanza excepcion, solo
    # informa si el cierre ya esta reflejado. Se usa para decidir, sin
    # abortar, si un push de un commit local ya existente sigue pendiente.
    param(
        [Parameter(Mandatory = $true)]
        [string] $Content,

        [Parameter(Mandatory = $true)]
        [string] $Slug
    )

    $state = Get-RoadmapState $Content $Slug
    return ($state.Done -eq 1 -and $state.Ready -eq 0)
}

function Test-RoadmapItemsClosedOnce {
    # Version booleana de Assert-RoadmapItemsClosedOnce (modo Milestone).
    param(
        [Parameter(Mandatory = $true)]
        [string] $Content,

        [Parameter(Mandatory = $true)]
        [string[]] $Items
    )

    foreach ($item in $Items) {
        if (-not (Test-RoadmapClosedOnce $Content $item)) {
            return $false
        }
    }

    return $true
}

function Confirm-PrMergedIntoBase {
    param(
        [Parameter(Mandatory = $true)]
        [string] $GitHubCliPath,

        [string] $Branch,

        [int] $PrNumber = 0,

        [Parameter(Mandatory = $true)]
        [string] $BaseBranch
    )

    $prRef = if ($PrNumber -gt 0) { $PrNumber.ToString() } else { $Branch }
    if ([string]::IsNullOrWhiteSpace($prRef)) {
        throw "Debe informarse Branch o PrNumber para confirmar la PR mergeada."
    }

    Write-Host "==> Confirmando en GitHub que la PR '$prRef' esta MERGED contra $BaseBranch..."
    $jsonText = Get-CheckedOutput $GitHubCliPath @(
        "pr", "view", $prRef,
        "--json", "state,mergedAt,baseRefName,headRefName,number"
    )

    $pr = $jsonText | ConvertFrom-Json
    if ($pr.state -ne "MERGED") {
        throw "La PR '$prRef' no esta mergeada. Estado informado por GitHub: $($pr.state)."
    }

    if ($pr.baseRefName -ne $BaseBranch) {
        throw "La PR '$prRef' fue mergeada contra '$($pr.baseRefName)', no contra '$BaseBranch'."
    }

    if ([string]::IsNullOrWhiteSpace($pr.mergedAt)) {
        throw "GitHub informa MERGED para '$prRef' pero no entrego mergedAt. No se continua."
    }

    if (-not [string]::IsNullOrWhiteSpace($Branch) -and $pr.headRefName -ne $Branch) {
        throw "La PR '$prRef' pertenece a head '$($pr.headRefName)', no a '$Branch'."
    }

    Write-Host "==> PR #$($pr.number) confirmada como MERGED en $BaseBranch ($($pr.mergedAt))."
}

function Remove-LocalFeatureArtifacts {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Branch,

        [Parameter(Mandatory = $true)]
        [string] $WorktreeDir
    )

    Write-Host "==> Limpiando worktree y rama local..."
    if (Test-Path -LiteralPath $WorktreeDir) {
        try { Invoke-Checked "git" @("worktree", "remove", $WorktreeDir) }
        catch { throw "Cleanup incompleto: no se pudo remover el worktree Git '$WorktreeDir'. No se fuerza el borrado de contenido." }
        Invoke-Checked "git" @("worktree", "prune")
        if (Test-Path -LiteralPath $WorktreeDir) {
            $entries = @(Get-ChildItem -LiteralPath $WorktreeDir -Force -ErrorAction SilentlyContinue)
            if ($entries.Count -gt 0) { throw "Cleanup incompleto: metadata Git removida pero el residual físico contiene archivos: $WorktreeDir" }
            Write-Warning "Residual físico vacío (posible lock Windows): $WorktreeDir"
        } else { Write-Host "==> Worktree eliminado: $WorktreeDir" }
    }
    else {
        Write-Host "==> No existe worktree local para eliminar: $WorktreeDir"
    }

    if (Test-GitSuccess @("rev-parse", "--verify", "--quiet", $Branch)) {
        Invoke-Checked "git" @("branch", "-d", $Branch)
        Write-Host "==> Rama local eliminada: $Branch"
    }
    else {
        Write-Host "==> No existe rama local para eliminar: $Branch"
    }
}

if ([string]::IsNullOrWhiteSpace($Branch)) {
    if ([string]::IsNullOrWhiteSpace($Slug)) {
        throw "Debe informarse Slug o Branch para cerrar la work unit."
    }
    $versionPrefix = if ([string]::IsNullOrWhiteSpace($Version)) { "" } else { "$Version-" }
    $Branch = if ($Mode -eq "Milestone") { "milestone/$versionPrefix$Slug" } elseif ($Mode -eq "Maintenance") { "maintenance/$versionPrefix$Slug" } else { "feature/$versionPrefix$Slug" }
}

if ($Mode -eq "Maintenance") {
    $maintenanceScope = Resolve-MaintenanceScope -Branch $Branch -Mode $Mode -Version $Version
    Write-Host "==> maintenance_scope: $($maintenanceScope.Scope)"
    if ($maintenanceScope.Scope -eq "canonical-unit") {
        $Slug = $maintenanceScope.CanonicalSlug
        Write-Host "==> Unidad canonica Maintenance resuelta: $Slug (rama: $Branch)"
    }
    else {
        $Slug = $maintenanceScope.BranchSlug
        Write-Host "==> close_roadmap: skipped"
        Write-Host "==> reason: $($maintenanceScope.Reason)"
    }
}
elseif ([string]::IsNullOrWhiteSpace($Slug)) {
    throw "Debe informarse Slug para cerrar una work unit $Mode."
}

$baseBranch = "develop"
$ghPath = Get-GitHubCliPath
$repoRoot = Get-CheckedOutput "git" @("rev-parse", "--show-toplevel")
$repoRoot = [System.IO.Path]::GetFullPath($repoRoot)

if ([string]::IsNullOrWhiteSpace($WorktreeDir)) {
    $worktreesRoot = Join-Path (Split-Path -Parent $repoRoot) "worktrees"
    $worktreePrefix = if ([string]::IsNullOrWhiteSpace($Version)) { "" } else { "$Version-" }
    $worktreeName = "$worktreePrefix$Slug"
    $WorktreeDir = Join-Path $worktreesRoot $worktreeName
}

$WorktreeDir = [System.IO.Path]::GetFullPath($WorktreeDir)
$currentDir = [System.IO.Path]::GetFullPath((Get-Location).Path)
if ($currentDir.StartsWith($WorktreeDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Estas dentro del worktree de la feature. Sali al checkout principal de develop antes de correr este script."
}

Confirm-PrMergedIntoBase -GitHubCliPath $ghPath -Branch $Branch -PrNumber $PrNumber -BaseBranch $baseBranch

Assert-CleanWorktree "antes de actualizar $baseBranch"

Write-Host "==> Actualizando referencias remotas..."
Invoke-Checked "git" @("fetch", "origin", $baseBranch, "--prune")

Write-Host "==> Cambiando al checkout principal de $baseBranch..."
Invoke-Checked "git" @("checkout", $baseBranch)
Assert-CleanWorktree "antes de sincronizar $baseBranch"

Write-Host "==> Sincronizando $baseBranch con origin/$baseBranch..."
Invoke-Checked "git" @("pull", "--ff-only", "origin", $baseBranch)
Assert-CleanWorktree "despues de sincronizar $baseBranch"

$roadmapPath = "ROADMAP.md"

if ($Mode -eq "Maintenance" -and $maintenanceScope.Scope -eq "auxiliary") {
    Write-Host "maintenance_scope: auxiliary"
    Write-Host "close_roadmap: skipped"
    Write-Host "reason: no canonical unit associated"
    if ($env:GITHUB_STEP_SUMMARY) {
        @(
            "### Maintenance lifecycle",
            '- maintenance_scope: auxiliary',
            '- close_roadmap: skipped',
            '- reason: no canonical unit associated'
        ) | Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY
    }
    if ($SkipLocalCleanup) {
        Write-Host "==> Limpieza local omitida por -SkipLocalCleanup."
    }
    else {
        Remove-LocalFeatureArtifacts $Branch $WorktreeDir
    }
    Assert-CleanWorktree "al finalizar"
    Write-Host "==> Maintenance auxiliar completada sin modificar ROADMAP.md."
    exit 0
}

if ($Mode -eq "Milestone") {
    $manifestPath = "runs/milestone-$Slug/work-unit.json"
    $manifest = Read-WorkUnitManifest -Path $manifestPath
    $items = @($manifest.Items)

    Write-Host "==> Validando estado de los items del milestone '$Slug' en ROADMAP.md..."
    $roadmap = Get-Content -LiteralPath $roadmapPath -Raw -Encoding UTF8
    $closeState = Assert-RoadmapItemsCanClose $roadmap $items

    if ($closeState -eq "already-closed") {
        Write-Host "==> Todos los items de '$Slug' ya estan marcados [x] localmente. Reejecucion segura, sin commit vacio."
        Write-Host "==> Verificando si el push del cierre esta pendiente en origin/$baseBranch..."
        Invoke-Checked "git" @("fetch", "origin", $baseBranch)
        $remoteRoadmapCheck = Get-CheckedOutput "git" @("show", "origin/$baseBranch`:ROADMAP.md")
        if (Test-RoadmapItemsClosedOnce $remoteRoadmapCheck $items) {
            Write-Host "==> El remoto ya tiene el cierre. Nada que pushear."
        }
        else {
            Write-Host "==> El remoto todavia no tiene el cierre. Pusheando commit local pendiente..."
            Invoke-Checked "git" @("push", "origin", $baseBranch)
        }
    }
    else {
        Write-Host "==> Marcando todos los items de '$Slug' como completados en ROADMAP.md..."
        $updatedRoadmap = $roadmap
        foreach ($item in $items) {
            $escapedItem = [regex]::Escape($item)
            $readyRegex = [regex]::new("(?m)^- \[-\] ($escapedItem(?=\s|$).*)$")
            $updatedRoadmap = $readyRegex.Replace($updatedRoadmap, '- [x] $1', 1)
        }
        Set-Content -LiteralPath $roadmapPath -Value $updatedRoadmap -Encoding UTF8

        $postUpdateRoadmap = Get-Content -LiteralPath $roadmapPath -Raw -Encoding UTF8
        Assert-RoadmapItemsClosedOnce $postUpdateRoadmap $items "despues de actualizar ROADMAP.md"

        Invoke-Checked "git" @("add", $roadmapPath)
        & git diff --cached --quiet
        if ($LASTEXITCODE -eq 0) {
            throw "La actualizacion de ROADMAP.md no produjo cambios staged. Se evita crear commit vacio."
        }

        Invoke-Checked "git" @("commit", "-m", "docs: cerrar milestone $Slug en ROADMAP.md ($($items -join ', '))")

        Write-Host "==> Pusheando cierre a origin/$baseBranch..."
        Invoke-Checked "git" @("push", "origin", $baseBranch)
    }

    Write-Host "==> Verificando cierre publicado en origin/$baseBranch..."
    Invoke-Checked "git" @("fetch", "origin", $baseBranch)
    $remoteRoadmap = Get-CheckedOutput "git" @("show", "origin/$baseBranch`:ROADMAP.md")
    Assert-RoadmapItemsClosedOnce $remoteRoadmap $items "en origin/$baseBranch"
}
else {
    Write-Host "==> Validando estado de '$Slug' en ROADMAP.md..."
    $roadmap = Get-Content -LiteralPath $roadmapPath -Raw -Encoding UTF8
    $closeState = Assert-RoadmapCanClose $roadmap $Slug

    if ($closeState -eq "already-closed") {
        Write-Host "==> $Slug ya esta marcada exactamente una vez como [x] localmente. Reejecucion segura, sin commit vacio."
        Write-Host "==> Verificando si el push del cierre esta pendiente en origin/$baseBranch..."
        Invoke-Checked "git" @("fetch", "origin", $baseBranch)
        $remoteRoadmapCheck = Get-CheckedOutput "git" @("show", "origin/$baseBranch`:ROADMAP.md")
        if (Test-RoadmapClosedOnce $remoteRoadmapCheck $Slug) {
            Write-Host "==> El remoto ya tiene el cierre. Nada que pushear."
        }
        else {
            Write-Host "==> El remoto todavia no tiene el cierre. Pusheando commit local pendiente..."
            Invoke-Checked "git" @("push", "origin", $baseBranch)
        }
    }
    else {
        Write-Host "==> Marcando '$Slug' como completada en ROADMAP.md..."
        $escapedSlug = [regex]::Escape($Slug)
        $readyRegex = [regex]::new("(?m)^- \[-\] ($escapedSlug(?=\s|$).*)$")
        $updatedRoadmap = $readyRegex.Replace($roadmap, '- [x] $1', 1)
        Set-Content -LiteralPath $roadmapPath -Value $updatedRoadmap -Encoding UTF8

        $postUpdateRoadmap = Get-Content -LiteralPath $roadmapPath -Raw -Encoding UTF8
        Assert-RoadmapClosedOnce $postUpdateRoadmap $Slug "despues de actualizar ROADMAP.md"

        Invoke-Checked "git" @("add", $roadmapPath)
        & git diff --cached --quiet
        if ($LASTEXITCODE -eq 0) {
            throw "La actualizacion de ROADMAP.md no produjo cambios staged. Se evita crear commit vacio."
        }

        Invoke-Checked "git" @("commit", "-m", "docs: cerrar $Slug en ROADMAP.md")

        Write-Host "==> Pusheando cierre a origin/$baseBranch..."
        Invoke-Checked "git" @("push", "origin", $baseBranch)
    }

    Write-Host "==> Verificando cierre publicado en origin/$baseBranch..."
    Invoke-Checked "git" @("fetch", "origin", $baseBranch)
    $remoteRoadmap = Get-CheckedOutput "git" @("show", "origin/$baseBranch`:ROADMAP.md")
    Assert-RoadmapClosedOnce $remoteRoadmap $Slug "en origin/$baseBranch"
}

if ($SkipLocalCleanup) {
    Write-Host "==> Limpieza local omitida por -SkipLocalCleanup. GitHub Actions no puede borrar worktrees del equipo local."
}
else {
    Remove-LocalFeatureArtifacts $Branch $WorktreeDir
}

Assert-CleanWorktree "al finalizar"
Write-Host "==> Listo. $Slug cerrada y validada en origin/$baseBranch."
