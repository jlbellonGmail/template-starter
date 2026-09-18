param(
    [Parameter(Mandatory = $true)]
    [string] $Slug,

    [int] $PrNumber = 0,

    [string] $Branch = "",

    [ValidateSet("Feature", "Milestone", "Maintenance")]
    [string] $Mode = "Feature",

    [string] $Version = "",

    [string] $BaseBranch = "",

    [ValidateSet("merge", "squash", "rebase")]
    [string] $MergeMethod = "merge",

    [string] $WorktreeDir = "",

    [int] $CheckPollSeconds = 10,

    [int] $CheckMaxMinutes = 60,

    [string] $IgnoredWorkflowName = "Post-HITL merge gate",

    [int] $LocalCleanupPollSeconds = 10,

    [int] $LocalCleanupMaxMinutes = 30,

    [switch] $SkipLocalCleanup,

    [switch] $CommentOnFailure

    ,
    [switch] $PreAuthorizedHumanMerge,

    [string] $AuthorizationPath = ""

    ,
    [ValidateSet("SingleMaintainer", "MultiMaintainer")]
    [string] $GovernanceMode = "MultiMaintainer",

    [string] $IndependentReviewPath = "",

    [string] $IntegrityEvidencePath = ""
)

$ErrorActionPreference = "Stop"

function Get-GitHubCliPath {
    $command = Get-Command gh -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $defaultPath = Join-Path $env:ProgramFiles "GitHub CLI\gh.exe"
    if (Test-Path -LiteralPath $defaultPath) {
        return $defaultPath
    }

    throw "GitHub CLI (gh) no esta disponible. Se requiere para completar una PR aprobada."
}

function Invoke-Gh {
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
        Text = $text.Trim()
    }
}

function Get-NextReportPath {
    param([Parameter(Mandatory = $true)][string] $Slug)

    $runDir = Join-Path "runs" $Slug
    if (-not (Test-Path -LiteralPath $runDir -PathType Container)) {
        New-Item -ItemType Directory -Path $runDir | Out-Null
    }

    $attempt = 1
    while (Test-Path -LiteralPath (Join-Path $runDir "post-hitl-gate-$attempt.md")) {
        $attempt += 1
    }

    return [pscustomobject]@{
        Attempt = $attempt
        Path = Join-Path $runDir "post-hitl-gate-$attempt.md"
    }
}

function Write-GateReport {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Slug,

        [Parameter(Mandatory = $true)]
        [ValidateSet("approved", "rejected")]
        [string] $Status,

        [Parameter(Mandatory = $true)]
        [string[]] $Feedback,

        [string] $Details = ""
    )

    $report = Get-NextReportPath -Slug $Slug
    $lines = New-Object System.Collections.Generic.List[string]
    [void] $lines.Add("status: $Status")
    [void] $lines.Add("attempt: $($report.Attempt)")
    [void] $lines.Add("feedback:")
    foreach ($item in $Feedback) {
        [void] $lines.Add("  - $item")
    }
    [void] $lines.Add("---")
    [void] $lines.Add("")
    [void] $lines.Add("# Post-HITL gate $($report.Attempt): $Slug")
    [void] $lines.Add("")
    if (-not [string]::IsNullOrWhiteSpace($Details)) {
        [void] $lines.Add("## Detalle")
        [void] $lines.Add("")
        [void] $lines.Add('```text')
        [void] $lines.Add($Details.Trim())
        [void] $lines.Add('```')
        [void] $lines.Add("")
    }

    [System.IO.File]::WriteAllText(
        (Join-Path (Get-Location).Path $report.Path),
        ($lines -join [Environment]::NewLine) + [Environment]::NewLine,
        (New-Object System.Text.UTF8Encoding($false))
    )

    return $report.Path
}

function Add-PrComment {
    param(
        [Parameter(Mandatory = $true)]
        [string] $GitHubCliPath,

        [Parameter(Mandatory = $true)]
        [string] $PrRef,

        [Parameter(Mandatory = $true)]
        [string] $ReportPath
    )

    $body = Get-Content -LiteralPath $ReportPath -Raw -Encoding UTF8
    $bodyFileName = "post-hitl-gate-{0}.md" -f ([guid]::NewGuid())
    $bodyPath = Join-Path -Path ([System.IO.Path]::GetTempPath()) -ChildPath $bodyFileName
    try {
        Set-Content -LiteralPath $bodyPath -Value $body -Encoding UTF8
        [void](Invoke-Gh -GitHubCliPath $GitHubCliPath -Arguments @("pr", "comment", $PrRef, "--body-file", $bodyPath))
    }
    finally {
        if (Test-Path -LiteralPath $bodyPath) {
            Remove-Item -LiteralPath $bodyPath -Force
        }
    }
}

function ConvertTo-ObjectArray {
    param($Value)

    if ($null -eq $Value) {
        return @()
    }

    if ($Value -is [array]) {
        return @($Value)
    }

    return @($Value)
}

function Format-Checks {
    param([object[]] $Checks)

    if ($Checks.Count -eq 0) {
        return "No se encontraron checks relevantes para la PR."
    }

    return (($Checks | ForEach-Object {
        $workflow = if ([string]::IsNullOrWhiteSpace($_.workflow)) { "sin workflow" } else { $_.workflow }
        $name = if ([string]::IsNullOrWhiteSpace($_.name)) { "sin nombre" } else { $_.name }
        "- [$($_.bucket)] $workflow / $name ($($_.state)) $($_.link)"
    }) -join [Environment]::NewLine)
}

function Get-LatestApprovedReviewCommit {
    # Consulta el historial completo de reviews de la PR (incluye
    # APPROVED/DISMISSED/CHANGES_REQUESTED/COMMENTED/PENDING de todos los
    # revisores) via 'gh api .../reviews --paginate --slurp'. '--slurp' es
    # necesario porque el endpoint devuelve un array JSON por pagina: sin
    # ese flag, 'gh api --paginate' concatenaria varios arrays JSON
    # adyacentes que no forman un unico JSON valido; con '--slurp', 'gh'
    # envuelve cada pagina (ya de por si un array) en un array exterior,
    # por lo que el resultado es un array de arrays que hay que aplanar.
    # Filtra por state=APPROVED y devuelve el commit_id de la review mas
    # reciente por 'submitted_at'. Devuelve $null si no hay ninguna
    # APPROVED (caso borde defensivo).
    param(
        [Parameter(Mandatory = $true)]
        [string] $GitHubCliPath,

        [Parameter(Mandatory = $true)]
        [string] $PrNumber
    )

    $result = Invoke-Gh -GitHubCliPath $GitHubCliPath -Arguments @(
        "api", "repos/:owner/:repo/pulls/$PrNumber/reviews",
        "--paginate", "--slurp"
    )

    $pages = if ([string]::IsNullOrWhiteSpace($result.Text)) {
        @()
    }
    else {
        ConvertTo-ObjectArray ($result.Text | ConvertFrom-Json)
    }

    $reviews = New-Object System.Collections.Generic.List[object]
    foreach ($page in $pages) {
        foreach ($review in (ConvertTo-ObjectArray $page)) {
            [void] $reviews.Add($review)
        }
    }

    $approved = @($reviews | Where-Object { $_.state -eq "APPROVED" })
    if ($approved.Count -eq 0) {
        return $null
    }

    $latest = $approved | Sort-Object { [datetime] $_.submitted_at } -Descending | Select-Object -First 1
    return $latest.commit_id
}

function Wait-PrChecks {
    param(
        [Parameter(Mandatory = $true)]
        [string] $GitHubCliPath,

        [Parameter(Mandatory = $true)]
        [string] $PrRef,

        [Parameter(Mandatory = $true)]
        [string] $IgnoredWorkflowName,

        [int] $PollSeconds = 10,

        [int] $MaxMinutes = 60
    )

    $deadline = (Get-Date).AddMinutes($MaxMinutes)
    $lastRelevantChecks = @()

    while ((Get-Date) -lt $deadline) {
        $result = Invoke-Gh -GitHubCliPath $GitHubCliPath -Arguments @(
            "pr", "checks", $PrRef,
            "--json", "bucket,completedAt,link,name,startedAt,state,workflow"
        ) -AllowedExitCodes @(0, 1, 8)

        try {
            $checks = if ([string]::IsNullOrWhiteSpace($result.Text)) {
                @()
            }
            else {
                ConvertTo-ObjectArray ($result.Text | ConvertFrom-Json)
            }
        }
        catch {
            # GitHub puede devolver una respuesta transitoria no JSON mientras
            # recalcula checks tras synchronize. Se reintenta dentro del
            # presupuesto; nunca se interpreta como verde.
            Write-Warning "Respuesta transitoria de gh pr checks; se reintenta: $($_.Exception.Message)"
            Start-Sleep -Seconds $PollSeconds
            continue
        }

        $lastRelevantChecks = @($checks | Where-Object { $_.workflow -ne $IgnoredWorkflowName })
        if ($lastRelevantChecks.Count -eq 0) {
            Start-Sleep -Seconds $PollSeconds
            continue
        }

        $failedChecks = @($lastRelevantChecks | Where-Object { $_.bucket -in @("fail", "cancel") })
        if ($failedChecks.Count -gt 0) {
            return [pscustomobject]@{
                Status = "failed"
                Details = Format-Checks $lastRelevantChecks
            }
        }

        $pendingChecks = @($lastRelevantChecks | Where-Object { $_.bucket -eq "pending" })
        if ($pendingChecks.Count -eq 0) {
            return [pscustomobject]@{
                Status = "passed"
                Details = Format-Checks $lastRelevantChecks
            }
        }

        Start-Sleep -Seconds $PollSeconds
    }

    return [pscustomobject]@{
        Status = "timeout"
        Details = Format-Checks $lastRelevantChecks
    }
}

if ([string]::IsNullOrWhiteSpace($Branch)) {
    $versionPrefix = if ([string]::IsNullOrWhiteSpace($Version)) { "" } else { "$Version-" }
    $Branch = if ($Mode -eq "Milestone") { "milestone/$versionPrefix$Slug" } elseif ($Mode -eq "Maintenance") { "maintenance/$versionPrefix$Slug" } else { "feature/$versionPrefix$Slug" }
}

if ([string]::IsNullOrWhiteSpace($BaseBranch)) {
    $BaseBranch = if ([string]::IsNullOrWhiteSpace($env:BASE_BRANCH)) { "develop" } else { $env:BASE_BRANCH }
}

$prRef = if ($PrNumber -gt 0) { $PrNumber.ToString() } else { $Branch }
$ghPath = Get-GitHubCliPath

Write-Host "==> Validando aprobacion humana de PR '$prRef'..."
$viewResult = Invoke-Gh -GitHubCliPath $ghPath -Arguments @(
    "pr", "view", $prRef,
    "--json", "number,state,baseRefName,headRefName,url,reviewDecision,headRefOid"
)
$pr = $viewResult.Text | ConvertFrom-Json

if ($pr.state -ne "OPEN") {
    throw "La PR '$prRef' debe estar OPEN para completar el gate post-HITL. Estado actual: $($pr.state)."
}

if ($pr.baseRefName -ne $BaseBranch) {
    throw "La PR '$prRef' apunta a '$($pr.baseRefName)', no a '$BaseBranch'."
}

if ($pr.headRefName -ne $Branch) {
    throw "La PR '$prRef' pertenece a head '$($pr.headRefName)', no a '$Branch'."
}

function Assert-PreAuthorizedHumanMerge {
    param([Parameter(Mandatory = $true)][string] $Path, [Parameter(Mandatory = $true)][string] $ExpectedScope)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "No existe la autorizacion previa requerida: $Path" }
    $authorization = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
    if ($authorization -notmatch '(?m)^decision:\s*MERGE\s*$' -or
        $authorization -notmatch "(?m)^scope:\s*$([regex]::Escape($ExpectedScope))\s*$" -or
        $authorization -notmatch '(?m)^phase:\s*(?:02|03|04|13|14|15|17)\s*$' -or
        $authorization -notmatch '(?m)^authorizedBy:\s*user-instruction\s*$') {
        throw "La autorizacion previa no tiene el formato/scope esperado para $ExpectedScope."
    }
}

function Assert-SingleMaintainerEvidence {
    param(
        [Parameter(Mandatory=$true)][string] $ReviewPath,
        [Parameter(Mandatory=$true)][string] $IntegrityPath,
        [Parameter(Mandatory=$true)][string] $ExpectedHead,
        [Parameter(Mandatory=$true)][string] $ExpectedBase,
        [Parameter(Mandatory=$true)][string] $ExpectedScope
    )
    if (-not (Test-Path -LiteralPath $ReviewPath -PathType Leaf)) {
        throw "SingleMaintainer requiere Reviewer independiente vigente: $ReviewPath"
    }
    $review = Get-Content -LiteralPath $ReviewPath -Raw -Encoding UTF8
    if ($review -notmatch '(?m)^status:\s*approved\s*$' -or
        $review -notmatch "(?m)^scope:\s*$([regex]::Escape($ExpectedScope))\s*$" -or
        ($review -notmatch "(?m)^head:\s*$([regex]::Escape($ExpectedHead))\s*$" -and $review -notmatch '(?m)^head:\s*HEAD\s*$') -or
        $review -notmatch "(?m)^base:\s*$([regex]::Escape($ExpectedBase))\s*$") {
        throw "Reviewer independiente ausente, rechazado o stale para '$ExpectedScope'."
    }
    if (-not (Test-Path -LiteralPath $IntegrityPath -PathType Leaf)) {
        throw "SingleMaintainer requiere evidencia check-integrity PASS: $IntegrityPath"
    }
    $integrity = Get-Content -LiteralPath $IntegrityPath -Raw -Encoding UTF8
    if ($integrity -notmatch '(?im)\bPASS\b' -or $integrity -match '(?im)\b(?:FAIL|TIMEOUT|ERROR)\b') {
        throw "La evidencia de integridad no es PASS vigente: $IntegrityPath"
    }
}

$preauthorized = $false
if ($PreAuthorizedHumanMerge) {
    if ([string]::IsNullOrWhiteSpace($AuthorizationPath)) { throw "-AuthorizationPath es obligatorio con -PreAuthorizedHumanMerge." }
    Assert-PreAuthorizedHumanMerge -Path $AuthorizationPath -ExpectedScope $Slug
    $preauthorized = $true
    Write-Host "==> Autorizacion humana previa explicita validada para '$Slug'.
Se conserva la aprobacion HITL normal como requisito por defecto."
}

if ($GovernanceMode -eq "SingleMaintainer") {
    if (-not $preauthorized) {
        throw "SingleMaintainer requiere autorización humana scoped explícita; no se fabrica self-review."
    }
    if ([string]::IsNullOrWhiteSpace($IndependentReviewPath) -or [string]::IsNullOrWhiteSpace($IntegrityEvidencePath)) {
        throw "SingleMaintainer requiere -IndependentReviewPath y -IntegrityEvidencePath."
    }
    Assert-SingleMaintainerEvidence -ReviewPath $IndependentReviewPath -IntegrityPath $IntegrityEvidencePath -ExpectedHead $pr.headRefOid -ExpectedBase $BaseBranch -ExpectedScope $Slug
    Write-Host "==> governance_mode: single-maintainer; approval_basis: scoped-human-authorization + independent-agent-review + CI + integrity"
}
else {
    Write-Host "==> governance_mode: multi-maintainer; approval_basis: GitHub human review + CI + integrity"
}

if (-not $preauthorized -and $pr.reviewDecision -ne "APPROVED") {
    throw "La PR '$prRef' todavia no tiene aprobacion HITL. reviewDecision=$($pr.reviewDecision)."
}

Write-Host "==> Verificando autorizacion vigente sobre el commit actual..."
$latestApprovedCommit = if ($preauthorized) { $pr.headRefOid } else { Get-LatestApprovedReviewCommit -GitHubCliPath $ghPath -PrNumber $pr.number }

    if (-not $preauthorized -and ([string]::IsNullOrWhiteSpace($latestApprovedCommit) -or $latestApprovedCommit -ne $pr.headRefOid)) {
    $reportPath = Write-GateReport `
        -Slug $Slug `
        -Status "rejected" `
        -Feedback @(
            "La aprobacion humana mas reciente de la PR $prRef quedo obsoleta: fue emitida sobre un commit distinto del head vigente ($($pr.headRefOid)), probablemente por un push posterior a la aprobacion.",
            "Se requiere que el humano vuelva a aprobar la revision sobre el commit vigente; esto no es una correccion de builder-agent."
        )

    if ($CommentOnFailure) {
        Add-PrComment -GitHubCliPath $ghPath -PrRef $prRef -ReportPath $reportPath
    }

    throw "Aprobacion HITL obsoleta para '$prRef'. Feedback: $reportPath"
}

Write-Host "==> Aprobacion vigente sobre el commit actual. Esperando checks post-aprobacion..."
$checks = Wait-PrChecks `
    -GitHubCliPath $ghPath `
    -PrRef $prRef `
    -IgnoredWorkflowName $IgnoredWorkflowName `
    -PollSeconds $CheckPollSeconds `
    -MaxMinutes $CheckMaxMinutes

if ($checks.Status -ne "passed") {
    $reportPath = Write-GateReport `
        -Slug $Slug `
        -Status "rejected" `
        -Feedback @(
            "Los checks post-HITL de la PR $prRef no terminaron en verde (estado: $($checks.Status)).",
            "Builder-agent debe corregir la rama $Branch y relanzar QA/ready-for-pr sin pedir otro checkpoint humano."
        ) `
        -Details $checks.Details

    if ($CommentOnFailure) {
        Add-PrComment -GitHubCliPath $ghPath -PrRef $prRef -ReportPath $reportPath
    }

    throw "Checks post-HITL fallidos para '$prRef'. Feedback para builder: $reportPath"
}

Write-Host "==> Checks verdes. Mergeando PR '$prRef'..."
$mergeFlag = switch ($MergeMethod) {
    "merge" { "--merge" }
    "squash" { "--squash" }
    "rebase" { "--rebase" }
}

[void](Invoke-Gh -GitHubCliPath $ghPath -Arguments @(
    "pr", "merge", $prRef, $mergeFlag, "--delete-branch"
))

$successReport = Write-GateReport `
    -Slug $Slug `
    -Status "approved" `
    -Feedback @(
        $(if ($preauthorized) { "Autorizacion humana previa explicita validada para esta ejecucion; no se uso auto-aprobacion de GitHub." } else { "PR $prRef aprobada por HITL, checks post-aprobacion verdes y merge ejecutado." }),
        "El cierre remoto de ROADMAP queda a cargo de post-merge-close-feature.yml."
    ) `
    -Details $checks.Details

Write-Host "==> PR mergeada. Evidencia: $successReport"

if ($SkipLocalCleanup -or $env:GITHUB_ACTIONS -eq "true") {
    Write-Host "==> Limpieza local omitida. El runner remoto no debe borrar worktrees locales."
    exit 0
}

$reconciler = Join-Path $PSScriptRoot "local-feature-reconcile.ps1"
if (-not (Test-Path -LiteralPath $reconciler -PathType Leaf)) {
    throw "No existe el reconciliador local esperado: $reconciler"
}

Write-Host "==> Esperando cierre remoto y limpieza local..."
$cleanupArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $reconciler,
    "-Slug", $Slug,
    "-Branch", $Branch,
    "-Mode", $Mode,
    "-Version", $Version,
    "-PollSeconds", $LocalCleanupPollSeconds,
    "-MaxMinutes", $LocalCleanupMaxMinutes
)
if (-not [string]::IsNullOrWhiteSpace($WorktreeDir)) {
    $cleanupArgs += @("-WorktreeDir", $WorktreeDir)
}

& powershell.exe @cleanupArgs
if ($LASTEXITCODE -ne 0) {
    throw "La PR fue mergeada, pero fallo la limpieza local. Reejecutar local-feature-reconcile.ps1 para $Slug."
}
