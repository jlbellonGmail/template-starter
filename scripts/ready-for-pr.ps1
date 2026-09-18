param(
    [Parameter(Mandatory = $true)]
    [string] $Slug,

    [string] $Title = "",

    [ValidateSet("Feature", "Milestone")]
    [string] $Mode = "Feature",

    [string] $Version = "",

    [string] $SddPath = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "feature-contract.ps1")

function Get-PowerShellPath {
    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwsh) {
        return $pwsh.Source
    }

    $windowsPowerShell = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if ($windowsPowerShell) {
        return $windowsPowerShell.Source
    }

    throw "PowerShell no esta disponible para iniciar el reconciliador local."
}

function Invoke-GhJson {
    param(
        [Parameter(Mandatory = $true)]
        [string] $GitHubCliPath,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments,

        [int[]] $AllowedExitCodes = @(0)
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $GitHubCliPath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    $text = ($output | ForEach-Object { $_.ToString() }) -join "`n"

    if ($AllowedExitCodes -notcontains $exitCode) {
        throw "Command failed: gh $($Arguments -join ' ')`n$text"
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        StdOut = if ($exitCode -eq 0) { $text.Trim() } else { "" }
        StdErr = if ($exitCode -eq 0) { "" } else { $text.Trim() }
    }
}

function Get-ExistingPr {
    param(
        [Parameter(Mandatory = $true)]
        [string] $GitHubCliPath,

        [Parameter(Mandatory = $true)]
        [string] $Branch
    )

    $result = Invoke-GhJson -GitHubCliPath $GitHubCliPath -Arguments @(
        "pr", "view", $Branch,
        "--json", "number,url,baseRefName,state",
        "--jq", "."
    ) -AllowedExitCodes @(0, 1)

    if ($result.ExitCode -eq 0 -and -not [string]::IsNullOrWhiteSpace($result.StdOut)) {
        return ($result.StdOut | ConvertFrom-Json)
    }

    $notFound = $result.StdErr -match "no pull requests found|not found|Could not resolve to a PullRequest"
    if ($notFound -or [string]::IsNullOrWhiteSpace($result.StdErr)) {
        return $null
    }

    throw "Error real consultando PR existente con gh: $($result.StdErr)"
}

if ([string]::IsNullOrWhiteSpace($Title)) {
    $Title = if ($Mode -eq "Milestone") { "Milestone $Slug" } else { "Feature $Slug" }
}

$baseBranch = if ([string]::IsNullOrWhiteSpace($env:BASE_BRANCH)) { "develop" } else { $env:BASE_BRANCH }
$currentBranch = Get-CheckedOutput "git" @("branch", "--show-current")

if ($Mode -eq "Milestone") {
    $manifestPath = "runs/milestone-$Slug/work-unit.json"
    $manifest = Read-WorkUnitManifest -Path $manifestPath
    $items = @($manifest.Items)
    $contractTitle = $Title -replace "^Milestone ", ""
    $info = Get-WorkUnitInfo -Slug $Slug -Title $contractTitle -Mode Milestone -Items $items -Version $Version
    $expectedBranchPrefix = "milestone/"
}
else {
    $contractTitle = $Title -replace "^Feature [0-9]{2}-", ""
    $info = Get-FeatureInfo -Slug $Slug -Title $contractTitle -Version $Version
    $expectedBranchPrefix = "feature/"
}

if ($currentBranch -eq $baseBranch -or $currentBranch -eq "main") {
    throw "Este script debe correr en una rama de feature, no en $currentBranch."
}

if (-not $currentBranch.StartsWith($expectedBranchPrefix)) {
    throw "La rama actual debe empezar con '$expectedBranchPrefix'. Rama actual: $currentBranch"
}

& git diff --quiet
$unstagedStatus = $LASTEXITCODE
& git diff --cached --quiet
$stagedStatus = $LASTEXITCODE
if ($unstagedStatus -ne 0 -or $stagedStatus -ne 0) {
    throw "Hay cambios sin commitear antes de marcar READY_FOR_PR. Commit de implementacion, tests y docs requerido."
}

$roadmapPath = "ROADMAP.md"
$roadmap = Get-Content -LiteralPath $roadmapPath -Raw -Encoding UTF8

if ($Mode -eq "Milestone") {
    $doneItems = @($items | Where-Object { (Get-RoadmapItemStateName -Content $roadmap -ItemSlug $_) -eq "Done" })
    if ($doneItems.Count -gt 0) {
        throw "$($doneItems -join ', ') ya figura(n) como [x]. No se puede marcar READY_FOR_PR despues del cierre."
    }

    $readyItems = @($items | Where-Object { (Get-RoadmapItemStateName -Content $roadmap -ItemSlug $_) -eq "Ready" })

    # GAP B: el contrato completo (decision.md, docs tecnica/usuario,
    # enlaces de indice, ultimo veredicto aprobado de auditoria/QA/code
    # review para TODOS los items del manifest) se valida antes de mutar
    # o commitear ROADMAP.md, en cualquiera de las dos ramas (incluida la
    # rama "todos ya Ready", que igual puede seguir hacia push/creacion de
    # PR mas adelante en el script). Se invoca sin -RequireReadyRoadmap:
    # ese switch se sigue exigiendo despues de la mutacion, sin cambios.
    Assert-WorkUnitContract -Slug $Slug -Mode Milestone -Title $info.Title -Version $Version -SddPath $SddPath

    if ($readyItems.Count -eq $items.Count) {
        Write-Host "==> Todos los items del milestone '$Slug' ya estan en READY_FOR_PR."
    }
    else {
        Assert-RoadmapItemsTransition -Content $roadmap -Items $items -FromStates @("Pending") -ToState "Ready"

        Write-Host "==> Marcando todos los items del milestone '$Slug' como READY_FOR_PR en ROADMAP.md..."
        $updatedRoadmap = $roadmap
        foreach ($item in $items) {
            $escapedItem = [regex]::Escape($item)
            $pendingRegex = [regex]::new("(?m)^- \[[ ~]\] ($escapedItem.*)$")
            $updatedRoadmap = $pendingRegex.Replace($updatedRoadmap, '- [-] $1', 1)
        }
        Set-Content -LiteralPath $roadmapPath -Value $updatedRoadmap -Encoding UTF8
        Invoke-Checked "git" @("add", $roadmapPath)
        Invoke-Checked "git" @("commit", "-m", "docs: marcar milestone $Slug como ready for PR ($($items -join ', '))")
    }

    Assert-WorkUnitContract -Slug $Slug -Mode Milestone -Title $info.Title -Version $Version -SddPath $SddPath -RequireReadyRoadmap
}
else {
    $escapedSlug = [regex]::Escape($Slug)

    if ($roadmap -match "(?m)^- \[x\] $escapedSlug\b") {
        throw "$Slug ya figura como [x]. No se puede marcar READY_FOR_PR despues del cierre."
    }

    # GAP B: mismo criterio que en Milestone (simetrico, ver observacion 2
    # de audit-1.md): la validacion completa del contrato corre antes de
    # cualquier mutacion/commit de ROADMAP.md, incluida la rama "ya esta
    # en READY_FOR_PR" (que igual puede seguir hacia push/creacion de PR).
    Assert-FeatureContract -Slug $Slug -Title $info.Title -Version $Version -SddPath $SddPath

    if ($roadmap -match "(?m)^- \[-\] $escapedSlug\b") {
        Write-Host "==> $Slug ya esta en READY_FOR_PR."
    }
    else {
        $pendingPattern = "(?m)^- \[[ ~]\] ($escapedSlug.*)$"
        if ($roadmap -notmatch $pendingPattern) {
            throw "No encontre '$Slug' pendiente en ROADMAP.md."
        }

        Write-Host "==> Marcando '$Slug' como READY_FOR_PR en ROADMAP.md..."
        $pendingRegex = [regex]::new($pendingPattern)
        $updatedRoadmap = $pendingRegex.Replace($roadmap, '- [-] $1', 1)
        Set-Content -LiteralPath $roadmapPath -Value $updatedRoadmap -Encoding UTF8
        Invoke-Checked "git" @("add", $roadmapPath)
        Invoke-Checked "git" @("commit", "-m", "docs: marcar $Slug como ready for PR")
    }

    Assert-FeatureContract -Slug $Slug -Title $info.Title -Version $Version -SddPath $SddPath -RequireReadyRoadmap
}

Write-Host "==> Pusheando $currentBranch..."
Invoke-Checked "git" @("push", "-u", "origin", $currentBranch)

$ghPath = Get-GitHubCliPath
$powerShellPath = Get-PowerShellPath
$existingPr = Get-ExistingPr -GitHubCliPath $ghPath -Branch $currentBranch
if ($null -ne $existingPr) {
    if ($existingPr.baseRefName -ne $baseBranch) {
        throw "La PR existente #$($existingPr.number) apunta a '$($existingPr.baseRefName)', no a '$baseBranch'."
    }
    Write-Host "==> PR existente: #$($existingPr.number) $($existingPr.url)"
    & $powerShellPath -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "local-feature-reconcile.ps1") -Slug $Slug -Branch $currentBranch -WorktreeDir (Get-Location).Path -Mode $Mode -Version $Version -StartBackground
    exit 0
}

# GAP C: la validacion de contrato ya corrida arriba (con o sin
# -RequireReadyRoadmap) garantiza que el ultimo intento de cada veredicto
# existe y esta approved, asi que aca solo resolvemos el path real (no
# repetimos la validacion de estado) para no referenciar el literal
# generico "-N.md" en el cuerpo de la PR.
$codeReviewArtifact = Get-LatestVerdictArtifact -Directory $info.RunDir -Prefix "code-review"

# Get-LatestVerdictArtifact devuelve `.Path` como ruta ABSOLUTA
# (System.IO.FileInfo.FullName resuelta contra el directorio actual del
# proceso). El cuerpo de la PR debe usar el mismo formato relativo
# (runs/<slug>/audit-N.md) que el resto de la seccion de evidencias
# ($info.RunDir), sin filtrar el path absoluto del filesystem de quien
# corrio el script. Se recompone la ruta relativa a partir de
# $info.RunDir (ya relativo) y el nombre de archivo real resuelto por
# Get-LatestVerdictArtifact, sin tocar la firma de esa funcion ni sus
# otros consumidores (p. ej. Assert-LatestVerdictApproved).
$policy = Get-EvidenceContract -RunDir $info.RunDir -SddPath $SddPath
$auditPath = if ($policy.Required -contains "audit") { $a = Get-LatestVerdictArtifact -Directory $info.RunDir -Prefix "audit"; "$($info.RunDir)/$(Split-Path -Leaf $a.Path)" } else { $null }
$qaPath = if ($policy.Required -contains "test-report") { $q = Get-LatestVerdictArtifact -Directory $info.RunDir -Prefix "test-report"; "$($info.RunDir)/$(Split-Path -Leaf $q.Path)" } else { $null }
$codeReviewPath = "$($info.RunDir)/$(Split-Path -Leaf $codeReviewArtifact.Path)"

$evidenceSection = if ($Mode -eq "Milestone") {
    $itemLines = ($info.Items | ForEach-Object {
        "- $($_.Slug): docs tecnica $($_.TechnicalDoc), docs usuario $($_.UserDoc)"
    }) -join "`n"
    @"
- Milestone: $Slug
- Rama: $currentBranch
- Estado de roadmap: READY_FOR_PR para todos los items, sin marcar [x]

## Items incluidos

$itemLines

## Evidencias

- SUMMARY: $($info.RunDir)/SUMMARY.md
$(if ($policy.Required -contains "spec") { "- Spec: $($info.RunDir)/spec.md" })
$(if ($policy.Required -contains "plan") { "- Plan: $($info.RunDir)/plan.md" })
$(if ($policy.Required -contains "tasks") { "- Tasks: $($info.RunDir)/tasks.md" })
$(if ($policy.Required -contains "decision") { "- Decision: $($info.Decision)" })
$(if ($auditPath) { "- Auditoria: $auditPath" })
$(if ($qaPath) { "- QA: $qaPath" })
- Code review: $codeReviewPath
"@
}
else {
    @"
- Feature: $Slug
- Rama: $currentBranch
- Estado de roadmap: READY_FOR_PR, sin marcar [x]

## Evidencias

- SUMMARY: $($info.RunDir)/SUMMARY.md
$(if ($policy.Required -contains "spec") { "- Spec: $($info.RunDir)/spec.md" })
$(if ($policy.Required -contains "plan") { "- Plan: $($info.RunDir)/plan.md" })
$(if ($policy.Required -contains "tasks") { "- Tasks: $($info.RunDir)/tasks.md" })
$(if ($policy.Required -contains "decision") { "- Decision: $($info.Decision)" })
$(if ($auditPath) { "- Auditoria: $auditPath" })
$(if ($qaPath) { "- QA: $qaPath" })
- Code review: $codeReviewPath
- Documentacion tecnica: $($info.TechnicalDoc)
- Documentacion de usuario: $($info.UserDoc)
- Indices: $($info.TechnicalIndex), $($info.UserIndex)
"@
}

$bodyPath = Join-Path ([System.IO.Path]::GetTempPath()) ("pr-body-{0}.md" -f ([guid]::NewGuid()))
$body = @"
## Resumen

$evidenceSection

## Checklist

- [ ] CI verde en GitHub Actions
- [ ] Aprobacion HITL: si se aprueba la PR, `post-hitl-merge-gate.yml` vuelve a esperar Actions y mergea solo en verde
- [ ] Tests reportados cuando el contrato los requiere$(if ($qaPath) { " en $qaPath" })
- [ ] Criterios de aceptacion cubiertos
- [ ] Decisiones documentadas en $($info.Decision)
- [ ] Indices de documentacion enlazan el servicio una sola vez
- [ ] Roadmap en READY_FOR_PR, no [x]

## Post-merge

Despues de la aprobacion humana, `post-hitl-merge-gate.yml` invoca
`scripts/complete-approved-pr.ps1`: si Actions queda verde, mergea; si falla,
devuelve feedback a builder y no mergea.

El cierre remoto de ROADMAP.md lo ejecuta GitHub Actions con `scripts/close-feature.ps1`.
El reconciliador local iniciado por `ready-for-pr.ps1` solo limpia worktree/rama cuando
`origin/develop` ya contiene `[x] $Slug`.
"@

try {
    Set-Content -LiteralPath $bodyPath -Value $body -Encoding UTF8
    Write-Host "==> Creando PR hacia $baseBranch..."
    # 'gh pr create' no soporta --json/--jq en todas las versiones de gh
    # (a diferencia de 'gh pr view'/'gh pr list'). En su forma normal
    # (sin --json), 'gh pr create' imprime unicamente la URL de la PR
    # creada en stdout; se parsea el numero desde ahi. No hace falta una
    # consulta aparte: si 'gh pr create' no lanzo error, el --base que le
    # pasamos ya fue aceptado por GitHub.
    $createResult = Invoke-GhJson -GitHubCliPath $ghPath -Arguments @(
        "pr", "create",
        "--base", $baseBranch,
        "--head", $currentBranch,
        "--title", $Title,
        "--body-file", $bodyPath
    )
    $prUrl = $createResult.StdOut.Trim()
    if ($prUrl -notmatch "/pull/(\d+)\s*$") {
        throw "No se pudo interpretar la URL de la PR creada por 'gh pr create': '$prUrl'"
    }
    Write-Host "==> PR creada: #$($Matches[1]) $prUrl"
}
finally {
    if (Test-Path -LiteralPath $bodyPath) {
        Remove-Item -LiteralPath $bodyPath -Force
    }
}

& $powerShellPath -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "local-feature-reconcile.ps1") -Slug $Slug -Branch $currentBranch -WorktreeDir (Get-Location).Path -Mode $Mode -Version $Version -StartBackground
