param(
    [Parameter(Mandatory = $true)]
    [string] $Role,

    [string] $Stage = "",

    [string] $Feature = "",

    [string] $Version = "",

    [string] $RunFile = "",

    [string] $Model = "",

    [string] $Variant = "",

    [string[]] $Fallback = @(),

    [string] $FailedModel = "",

    [string] $FailureReason = "",

    [string] $EvidencePath = "",

    [switch] $AllowMissingCredentials,

    [switch] $NoEvidence,

    [switch] $UseLiveCatalog,

    [string[]] $Capabilities = @(),
    [ValidateSet("LOW", "MEDIUM", "HIGH")][string] $Risk = "",
    [ValidateSet("LIGHT", "STANDARD", "FULL")][string] $SddLevel = "",
    [int] $ContextTokens = 0,
    [ValidateSet("LIGHT", "STANDARD", "FULL")][string] $SecurityProfile = "",
    [string] $EvalEvidencePath = "",
    [string[]] $AvailableAliases = @()
)

$ErrorActionPreference = "Stop"
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
$selectedForEvidence = $null
$selectionOriginForEvidence = "unresolved"

function Get-RepositoryRoot {
    $root = (& git rev-parse --show-toplevel) -join "`n"
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($root)) {
        return [System.IO.Path]::GetFullPath($root.Trim())
    }

    return [System.IO.Path]::GetFullPath((Get-Location).Path)
}

function Read-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "No existe el archivo canonico requerido: $Path"
    }

    return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json)
}

function ConvertFrom-MinimalRunYaml {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Path
    )

    $execution = [ordered] @{
        model = "default"
        variant = "default"
        fallback = @()
    }

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return [pscustomobject] $execution
    }

    $inExecution = $false
    $inFallback = $false
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $withoutComment = ($line -replace '\s+#.*$', '').TrimEnd()
        if ([string]::IsNullOrWhiteSpace($withoutComment)) {
            continue
        }

        if ($withoutComment -match '^execution:\s*$') {
            $inExecution = $true
            $inFallback = $false
            continue
        }

        if (-not $inExecution) {
            continue
        }

        if ($withoutComment -match '^\s{2}model:\s*(.+?)\s*$') {
            $execution.model = ConvertFrom-YamlScalar $Matches[1]
            $inFallback = $false
            continue
        }

        if ($withoutComment -match '^\s{2}variant:\s*(.+?)\s*$') {
            $execution.variant = ConvertFrom-YamlScalar $Matches[1]
            $inFallback = $false
            continue
        }

        if ($withoutComment -match '^\s{2}fallback:\s*$') {
            $inFallback = $true
            continue
        }

        if ($inFallback -and $withoutComment -match '^\s{4}-\s*(.+?)\s*$') {
            $execution.fallback += ,(ConvertFrom-YamlScalar $Matches[1])
            continue
        }

        throw "run.yaml contiene una clave no soportada por la interfaz minima del punto 1: '$line'"
    }

    return [pscustomobject] $execution
}

function ConvertFrom-YamlScalar {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Value
    )

    $trimmed = $Value.Trim()
    if (($trimmed.StartsWith("'") -and $trimmed.EndsWith("'")) -or
        ($trimmed.StartsWith('"') -and $trimmed.EndsWith('"'))) {
        return $trimmed.Substring(1, $trimmed.Length - 2)
    }

    return $trimmed
}

function Split-ModelRef {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ModelRef
    )

    $parts = $ModelRef.Split("/", 2)
    if ($parts.Count -ne 2 -or [string]::IsNullOrWhiteSpace($parts[0]) -or [string]::IsNullOrWhiteSpace($parts[1])) {
        throw "Modelo invalido '$ModelRef'. Usa opencode-go/<modelo>, opencode/<modelo> u openrouter/<proveedor>/<modelo>."
    }

    return [pscustomobject] @{
        Provider = $parts[0]
        Model = $parts[1]
        Ref = $ModelRef
    }
}

function Get-ProviderConfig {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Models,

        [Parameter(Mandatory = $true)]
        [string] $Provider
    )

    $property = $Models.providers.PSObject.Properties[$Provider]
    if ($null -eq $property) {
        throw "Proveedor desconocido o no autorizado: $Provider"
    }

    return $property.Value
}

function Assert-ModelAllowed {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Models,

        [Parameter(Mandatory = $true)]
        [string] $ModelRef
    )

    $split = Split-ModelRef $ModelRef
    $providerConfig = Get-ProviderConfig -Models $Models -Provider $split.Provider
    $allowed = @($providerConfig.models)
    if ($allowed -notcontains $split.Model) {
        throw "Modelo no autorizado o inexistente para $($split.Provider): $($split.Model)"
    }

    return [pscustomobject] @{
        Provider = $split.Provider
        Model = $split.Model
        Ref = $split.Ref
        ProviderConfig = $providerConfig
    }
}

function Test-ProviderCredentials {
    param(
        [Parameter(Mandatory = $true)]
        [object] $ProviderConfig
    )

    if ($AllowMissingCredentials) {
        return $true
    }

    foreach ($name in @($ProviderConfig.credentialEnv)) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $true
        }
    }

    return $false
}

function Test-EnvAvailable {
    param([object] $Implementation)
    if ($AllowMissingCredentials) { return $true }
    $envs = @($Implementation.availabilityEnv)
    if ($envs.Count -eq 0) { return $true }
    foreach ($name in $envs) { if (-not [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable([string]$name))) { return $true } }
    return $false
}

function Read-EvalSignal {
    param([string] $Path)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    $summary = $null
    foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try { $row = $line | ConvertFrom-Json } catch { throw "Evidencia de evals invalida: $Path" }
        if ($null -ne $row.passRate) { $summary = $row }
    }
    if ($null -eq $summary) { return [pscustomobject]@{ usable = $false; source = $Path; reason = "sin resumen passRate" } }
    $rate = [double]$summary.passRate
    return [pscustomobject]@{ usable = ($rate -ge 0 -and $rate -le 1); passRate = $rate; source = $Path; reason = "senal relativa del resumen F07" }
}

function Resolve-DynamicCandidate {
    param([object] $Routing, [string] $Role, [string[]] $Required, [string] $Depth, [string] $Profile, [int] $Context, [string[]] $AllowedAliases, [object] $Models)
    $weights = $Routing.depthWeights.$Depth
    if ($null -eq $weights) { throw "Nivel SDD no tiene politica de routing: $Depth" }
    $roleCaps = @($Routing.roleCapabilities.$Role)
    if ($Required.Count -eq 0) { $Required = $roleCaps }
    $options = @()
    foreach ($item in @($Routing.implementations)) {
        if ($AllowedAliases.Count -gt 0 -and $AllowedAliases -notcontains [string]$item.alias) { continue }
        $caps = @($item.capabilities)
        if (@($Required | Where-Object { $caps -notcontains $_ }).Count -gt 0) { continue }
        if ($Context -gt 0 -and [int]$item.context -lt $Context) { continue }
        if ($Profile -and @($item.securityProfiles) -notcontains $Profile) { continue }
        $provider = Get-ProviderConfig -Models $Models -Provider ([string]$item.provider)
        if (-not $AllowMissingCredentials -and (-not (Test-EnvAvailable $item) -or -not (Test-ProviderCredentials $provider))) { continue }
        $score = ([double]$item.quality * [double]$weights.quality) - ([double]$item.cost * [double]$weights.cost) - ([double]$item.latency * [double]$weights.latency)
        $options += [pscustomobject]@{ item=$item; score=$score }
    }
    if ($options.Count -eq 0) { throw "BLOCKED: ninguna implementacion disponible satisface las capacidades, contexto y seguridad requeridos para $Role." }
    return ($options | Sort-Object @{Expression={$_.score};Descending=$true}, @{Expression={$_.item.alias};Descending=$false} | Select-Object -First 1).item
}

function Get-FallbackLabels {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Declaration,

        [string[]] $ExplicitFallback
    )

    if ($ExplicitFallback.Count -gt 0) {
        $labels = New-Object System.Collections.Generic.List[string]
        foreach ($value in $ExplicitFallback) {
            foreach ($label in ($value -split ",")) {
                $trimmed = $label.Trim()
                if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
                    [void] $labels.Add($trimmed)
                }
            }
        }
        return @($labels)
    }

    if ($Declaration.fallback -and @($Declaration.fallback).Count -gt 0) {
        return @($Declaration.fallback)
    }

    return @("go", "zen")
}

function New-Candidate {
    param(
        [Parameter(Mandatory = $true)]
        [string] $ModelRef,

        [Parameter(Mandatory = $true)]
        [string] $Variant,

        [Parameter(Mandatory = $true)]
        [string] $Origin,

        [string] $Label = ""
    )

    return [pscustomobject] @{
        ModelRef = $ModelRef
        Variant = $Variant
        Origin = $Origin
        Label = $Label
    }
}

function Add-Candidate {
    param(
        [System.Collections.Generic.List[object]] $Candidates,

        [Parameter(Mandatory = $true)]
        [object] $Candidate
    )

    foreach ($existing in $Candidates) {
        if ($existing.ModelRef -eq $Candidate.ModelRef -and $existing.Variant -eq $Candidate.Variant) {
            return
        }
    }
    [void] $Candidates.Add($Candidate)
}

function Write-Evidence {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Event,

        [string] $Path
    )

    if ($NoEvidence) {
        return
    }

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "Para registrar evidencia, indica -Feature o -EvidencePath. Usa -NoEvidence solo en validaciones sin ejecucion."
    }

    $parent = Split-Path -Parent $Path
    if (-not [string]::IsNullOrWhiteSpace($parent) -and -not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }

    $json = $Event | ConvertTo-Json -Depth 50 -Compress
    $writer = New-Object System.IO.StreamWriter($Path, $true, (New-Object System.Text.UTF8Encoding($false)))
    try {
        $writer.WriteLine($json)
    }
    finally {
        $writer.Dispose()
    }
}

try {
    if ($UseLiveCatalog) {
        if ($env:AGENTIC_TEST_MODE -eq "1") {
            throw "AGENTIC_TEST_MODE impide consultas de catalogo o llamadas que puedan consumir creditos reales."
        }
        throw "La interfaz minima del punto 1 no consulta catalogos remotos. Actualiza .agentic/models.json tras revisar disponibilidad oficial."
    }

    $root = Get-RepositoryRoot
    $models = Read-JsonFile (Join-Path $root ".agentic/models.json")

    # Los nombres históricos siguen aceptándose como interfaz de migración,
    # pero se resuelven siempre a un rol canónico por capacidad.
    $requestedRole = $Role
    $aliasProperty = $models.roleAliases.PSObject.Properties[$Role]
    if ($null -ne $aliasProperty) {
        $Role = [string]$aliasProperty.Value
    }
    $roleProperty = $models.roles.PSObject.Properties[$Role]
    if ($null -eq $roleProperty) {
        throw "Rol desconocido: $requestedRole"
    }
    $roleConfig = $roleProperty.Value

    if ([string]::IsNullOrWhiteSpace($SddLevel)) { $SddLevel = if ($models.routing.defaultSdd) { [string]$models.routing.defaultSdd } else { "STANDARD" } }
    if ([string]::IsNullOrWhiteSpace($SecurityProfile)) { $SecurityProfile = $SddLevel }
    $Capabilities = @($Capabilities | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $AvailableAliases = @($AvailableAliases | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $evalSignal = $null
    if (-not [string]::IsNullOrWhiteSpace($EvalEvidencePath)) {
        if (-not [System.IO.Path]::IsPathRooted($EvalEvidencePath)) { $EvalEvidencePath = Join-Path $root $EvalEvidencePath }
        $evalSignal = Read-EvalSignal $EvalEvidencePath
    }

    if ([string]::IsNullOrWhiteSpace($Stage)) {
        $Stage = $Role
    }

    if ([string]::IsNullOrWhiteSpace($RunFile) -and -not [string]::IsNullOrWhiteSpace($Feature)) {
        $runPrefix = if ([string]::IsNullOrWhiteSpace($Version)) { "runs" } else { "runs/$Version" }
        $RunFile = Join-Path $root ("$runPrefix/$Feature/run.yaml" -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    }
    elseif (-not [string]::IsNullOrWhiteSpace($RunFile) -and -not [System.IO.Path]::IsPathRooted($RunFile)) {
        $RunFile = Join-Path $root $RunFile
    }

    $declaration = [pscustomobject] @{
        model = "default"
        variant = "default"
        fallback = @()
    }
    if (-not [string]::IsNullOrWhiteSpace($RunFile)) {
        $declaration = ConvertFrom-MinimalRunYaml -Path $RunFile
    }

    $selectedModel = $roleConfig.default.model
    $modelOrigin = "role-default"
    if ($declaration.model -and $declaration.model -ne "default") {
        $selectedModel = $declaration.model
        $modelOrigin = "run-yaml"
    }
    if (-not [string]::IsNullOrWhiteSpace($Model)) {
        $selectedModel = $Model
        $modelOrigin = "explicit-parameter"
    }

    $selectedVariant = $roleConfig.default.variant
    $variantOrigin = "role-default"
    if ($declaration.variant -and $declaration.variant -ne "default") {
        $selectedVariant = $declaration.variant
        $variantOrigin = "run-yaml"
    }
    if (-not [string]::IsNullOrWhiteSpace($Variant)) {
        $selectedVariant = $Variant
        $variantOrigin = "explicit-parameter"
    }

    $dynamic = $Capabilities.Count -gt 0 -or $Risk -or $ContextTokens -gt 0 -or $EvalEvidencePath -or $AvailableAliases.Count -gt 0
    if ($dynamic -and $models.routing -and @($models.routing.implementations).Count -gt 0) {
        $dynamicItem = Resolve-DynamicCandidate -Routing $models.routing -Role $Role -Required $Capabilities -Depth $SddLevel -Profile $SecurityProfile -Context $ContextTokens -AllowedAliases $AvailableAliases -Models $models
        $selectedModel = "$($dynamicItem.provider)/$($dynamicItem.model)"
        $selectedVariant = if ($SddLevel -eq "FULL") { "high" } elseif ($SddLevel -eq "LIGHT") { "medium" } else { "high" }
        $modelOrigin = "capability-routing"
    }

    if (@($models.validVariants) -notcontains $selectedVariant) {
        throw "Variante invalida o no autorizada: $selectedVariant"
    }

    $primary = Assert-ModelAllowed -Models $models -ModelRef $selectedModel
    $selectedForEvidence = $primary
    $selectionOriginForEvidence = $modelOrigin
    $fallbackLabels = Get-FallbackLabels -Declaration $declaration -ExplicitFallback $Fallback
    $candidates = New-Object System.Collections.Generic.List[object]
    Add-Candidate -Candidates $candidates -Candidate (New-Candidate -ModelRef $selectedModel -Variant $selectedVariant -Origin $modelOrigin)

    foreach ($label in $fallbackLabels) {
        $fallbackMatch = $null
        foreach ($candidate in @($roleConfig.fallback)) {
            if ($candidate.label -eq $label) {
                $fallbackMatch = $candidate
                break
            }
        }

        if ($null -eq $fallbackMatch) {
            throw "Fallback no autorizado para ${Role}: $label"
        }

        if (@($models.validVariants) -notcontains $fallbackMatch.variant) {
            throw "Variante invalida en fallback $label para ${Role}: $($fallbackMatch.variant)"
        }

        $allowedCandidate = Assert-ModelAllowed -Models $models -ModelRef $fallbackMatch.model
        if ($allowedCandidate.ProviderConfig.requiresExplicitFallback -and @($fallbackLabels) -notcontains $label) {
            throw "El proveedor $($allowedCandidate.Provider) requiere fallback explicito."
        }

        Add-Candidate -Candidates $candidates -Candidate (New-Candidate -ModelRef $fallbackMatch.model -Variant $fallbackMatch.variant -Origin "fallback:$label" -Label $label)
    }

    $unavailable = New-Object System.Collections.Generic.List[string]
    $chosen = $null
    foreach ($candidate in $candidates) {
        if (-not [string]::IsNullOrWhiteSpace($FailureReason)) {
            $modelToSkip = if ([string]::IsNullOrWhiteSpace($FailedModel)) { $selectedModel } else { $FailedModel }
            if ($candidate.ModelRef -eq $modelToSkip) {
                [void] $unavailable.Add("$($candidate.ModelRef): $FailureReason")
                continue
            }
        }

        $allowed = Assert-ModelAllowed -Models $models -ModelRef $candidate.ModelRef
        if (-not (Test-ProviderCredentials -ProviderConfig $allowed.ProviderConfig)) {
            $envNames = @($allowed.ProviderConfig.credentialEnv) -join ", "
            [void] $unavailable.Add("$($candidate.ModelRef): faltan credenciales o marca de disponibilidad ($envNames)")
            continue
        }

        $chosen = [pscustomobject] @{
            Candidate = $candidate
            Allowed = $allowed
        }
        break
    }

    if ($null -eq $chosen) {
        $details = if ($unavailable.Count -gt 0) { " Detalle: $($unavailable -join '; ')" } else { "" }
        throw "No hay modelos disponibles con el fallback autorizado para $Role.$details"
    }

    $stopwatch.Stop()
    $fallbackApplied = $chosen.Candidate.ModelRef -ne $selectedModel -or -not [string]::IsNullOrWhiteSpace($FailureReason)
    $event = [ordered] @{
        execution_id = [guid]::NewGuid().ToString("N")
        feature = if ([string]::IsNullOrWhiteSpace($Feature)) { "ad-hoc" } else { $Feature }
        agent = $Role
        stage = $Stage
        provider = $chosen.Allowed.Provider
        model = $chosen.Allowed.Model
        model_ref = $chosen.Allowed.Ref
        variant = $chosen.Candidate.Variant
        model_selection_origin = $chosen.Candidate.Origin
        variant_selection_origin = $variantOrigin
        fallback_applied = [bool] $fallbackApplied
        fallback_from = if ($fallbackApplied) { if ([string]::IsNullOrWhiteSpace($FailedModel)) { $selectedModel } else { $FailedModel } } else { $null }
        fallback_reason = if ([string]::IsNullOrWhiteSpace($FailureReason)) { $null } else { $FailureReason }
        date = (Get-Date).ToUniversalTime().ToString("o")
        duration_ms = [int] $stopwatch.ElapsedMilliseconds
        result = "resolved"
        cost = $null
        capabilities_required = @($Capabilities)
        risk = if ($Risk) { $Risk } else { $null }
        sdd_level = $SddLevel
        context_tokens = $ContextTokens
        security_profile = $SecurityProfile
        eval_signal = $evalSignal
        eval_evidence_path = if ($EvalEvidencePath) { $EvalEvidencePath } else { $null }
        selection_reason = if ($modelOrigin -eq "capability-routing") { "capabilities + SDD/risk policy + availability/cost/latency; deterministic tie-break by alias" } else { "legacy role default/fallback" }
        opencode = [ordered] @{
            model = $chosen.Allowed.Ref
            variant = $chosen.Candidate.Variant
            args = @("--model", $chosen.Allowed.Ref)
        }
    }

    if ([string]::IsNullOrWhiteSpace($EvidencePath) -and -not [string]::IsNullOrWhiteSpace($Feature)) {
        $runPrefix = if ([string]::IsNullOrWhiteSpace($Version)) { "runs" } else { "runs/$Version" }
        $EvidencePath = Join-Path $root ("$runPrefix/$Feature/model-routing.jsonl" -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    }
    elseif (-not [string]::IsNullOrWhiteSpace($EvidencePath) -and -not [System.IO.Path]::IsPathRooted($EvidencePath)) {
        $EvidencePath = Join-Path $root $EvidencePath
    }

    Write-Evidence -Event ([pscustomobject] $event) -Path $EvidencePath
    $event | ConvertTo-Json -Depth 50
    exit 0
}
catch {
    $stopwatch.Stop()
    $failureEvent = [ordered] @{
        execution_id = [guid]::NewGuid().ToString("N")
        feature = if ([string]::IsNullOrWhiteSpace($Feature)) { "ad-hoc" } else { $Feature }
        agent = $Role
        stage = if ([string]::IsNullOrWhiteSpace($Stage)) { $Role } else { $Stage }
        provider = if ($selectedForEvidence) { $selectedForEvidence.Provider } else { $null }
        model = if ($selectedForEvidence) { $selectedForEvidence.Model } else { $Model }
        model_ref = if ($selectedForEvidence) { $selectedForEvidence.Ref } else { $Model }
        variant = $Variant
        model_selection_origin = $selectionOriginForEvidence
        fallback_applied = -not [string]::IsNullOrWhiteSpace($FailureReason)
        fallback_from = if ([string]::IsNullOrWhiteSpace($FailedModel)) { $null } else { $FailedModel }
        fallback_reason = if ([string]::IsNullOrWhiteSpace($FailureReason)) { $_.Exception.Message } else { $FailureReason }
        date = (Get-Date).ToUniversalTime().ToString("o")
        duration_ms = [int] $stopwatch.ElapsedMilliseconds
        result = "failed"
        error = $_.Exception.Message
        cost = $null
    }

    if ([string]::IsNullOrWhiteSpace($EvidencePath) -and -not [string]::IsNullOrWhiteSpace($Feature)) {
        $rootForFailure = Get-RepositoryRoot
        $runPrefix = if ([string]::IsNullOrWhiteSpace($Version)) { "runs" } else { "runs/$Version" }
        $EvidencePath = Join-Path $rootForFailure ("$runPrefix/$Feature/model-routing.jsonl" -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    }
    elseif (-not [string]::IsNullOrWhiteSpace($EvidencePath) -and -not [System.IO.Path]::IsPathRooted($EvidencePath)) {
        $rootForFailure = Get-RepositoryRoot
        $EvidencePath = Join-Path $rootForFailure $EvidencePath
    }

    if (-not $NoEvidence -and -not [string]::IsNullOrWhiteSpace($EvidencePath)) {
        Write-Evidence -Event ([pscustomobject] $failureEvent) -Path $EvidencePath
    }

    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
