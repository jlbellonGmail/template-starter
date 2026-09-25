# Semántica única del snapshot de STATUS.md.
# Este archivo no lee STATUS.md ni runs/ para decidir el presente: ambos son
# salida/evidencia histórica. update-status y check-status consumen estas
# mismas funciones.

$ErrorActionPreference = "Stop"

function Invoke-StatusGit {
    param([Parameter(Mandatory)][string[]]$Arguments)
    $out = & git @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git command failed: $($Arguments -join ' ')" }
    return (($out | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine).Trim()
}

function Invoke-StatusExternal {
    param([Parameter(Mandatory)][string]$File, [Parameter(Mandatory)][string[]]$Arguments)
    if ([string]::IsNullOrWhiteSpace($File)) { return [pscustomobject]@{ Code = 127; Text = "" } }
    $psi = [Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $File; $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
    foreach ($a in $Arguments) { [void]$psi.ArgumentList.Add($a) }
    $p = [Diagnostics.Process]::new(); $p.StartInfo = $psi
    if (-not $p.Start()) { return [pscustomobject]@{ Code = 127; Text = "" } }
    if (-not $p.WaitForExit(10000)) { try { $p.Kill() } catch {}; return [pscustomobject]@{ Code = 124; Text = "timeout" } }
    [pscustomobject]@{ Code = $p.ExitCode; Text = $p.StandardOutput.ReadToEnd().Trim() }
}

function Get-StatusGhJson {
    param([string]$Gh, [Parameter(Mandatory)][string[]]$Arguments)
    if ([string]::IsNullOrWhiteSpace($Gh)) { return [pscustomobject]@{ Available = $false; Value = $null; Error = "gh no disponible" } }
    $r = Invoke-StatusExternal $Gh $Arguments
    if ($r.Code -ne 0) { return [pscustomobject]@{ Available = $false; Value = $null; Error = $r.Text } }
    try { return [pscustomobject]@{ Available = $true; Value = ($r.Text | ConvertFrom-Json); Error = "" } }
    catch { return [pscustomobject]@{ Available = $false; Value = $null; Error = "respuesta JSON inválida" } }
}

function Get-StatusVersion {
    param([string]$Root, [string]$Branch)
    $sources = @()
    foreach ($name in @("VERSION", "version.txt", ".version")) {
        $path = Join-Path $Root $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $v = (Get-Content -LiteralPath $path -Raw -Encoding UTF8).Trim()
            if ($v -match '^v?(\d+\.\d+\.\d+)$') { $sources += [pscustomobject]@{ Value = "v$($Matches[1])"; Source = $name } }
        }
    }
    foreach ($path in @(Join-Path $Root "pyproject.toml", (Join-Path $Root "package.json"))) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $raw = Get-Content -LiteralPath $path -Raw -Encoding UTF8
            if ($path -like "*package.json" -and $raw -match '"version"\s*:\s*"(\d+\.\d+\.\d+)"') { $sources += [pscustomobject]@{ Value="v$($Matches[1])"; Source=(Split-Path $path -Leaf) } }
            elseif ($path -like "*pyproject.toml" -and $raw -match '(?m)^version\s*=\s*["''](\d+\.\d+\.\d+)["'']') { $sources += [pscustomobject]@{ Value="v$($Matches[1])"; Source=(Split-Path $path -Leaf) } }
        }
    }
    if ($sources.Count -gt 0) { return [ordered]@{ value=$sources[0].Value; source=$sources[0].Source; confidence="explicit" } }
    if ($Branch -match '(?i)(?:^|/)(?:feature|milestone|maintenance)/(?<v>v\d+\.\d+\.\d+)-') { return [ordered]@{ value=$Matches.v; source="branch"; confidence="explicit" } }
    $roadmapPath = Join-Path $Root "ROADMAP.md"
    if (Test-Path -LiteralPath $roadmapPath -PathType Leaf) {
        $raw = Get-Content -LiteralPath $roadmapPath -Raw -Encoding UTF8
        $versions = @([regex]::Matches($raw, '(?im)^##\s+(?<v>v\d+\.\d+\.\d+).*Roadmap activo') | ForEach-Object { $_.Groups['v'].Value })
        if ($versions.Count -gt 0) {
            $best = $versions | Sort-Object { [version]($_ -replace '^v','') } -Descending | Select-Object -First 1
            return [ordered]@{ value=$best; source="ROADMAP.md"; confidence="declared" }
        }
    }
    $tagText = Invoke-StatusGit @('tag','--sort=-version:refname')
    $latestTag = @($tagText -split "`r?`n" | Where-Object { $_ -match '^v\d+\.\d+\.\d+$' } | Select-Object -First 1)
    if ($latestTag.Count -gt 0) { return [ordered]@{ value=$latestTag[0]; source="git tag"; confidence="release-fallback" } }
    return [ordered]@{ value=$null; source=$null; confidence="unknown" }
}

function Get-StatusWorktrees {
    param([string]$Raw, [string]$PrimaryPath)
    $items = @(); $path = $null; $branch = $null; $head = $null
    foreach ($line in ($Raw -split "`r?`n")) {
        if ($line -match '^worktree (.+)$') { $path=$Matches[1].Trim(); $branch=$null; $head=$null }
        elseif ($line -match '^HEAD (.+)$' -and $path) { $head=$Matches[1].Trim() }
        elseif ($line -match '^branch (.+)$' -and $path) { $branch=$Matches[1].Trim() -replace '^refs/heads/','' }
        elseif ([string]::IsNullOrWhiteSpace($line) -and $path) {
            $items += [ordered]@{ path=$path; branch=if($branch){$branch}else{"(detached)"}; head=$head; role=if([IO.Path]::GetFullPath($path) -eq [IO.Path]::GetFullPath($PrimaryPath)){"primary"}else{"linked"}; gitActive=$true }
            $path=$null
        }
    }
    if ($path) { $items += [ordered]@{ path=$path; branch=if($branch){$branch}else{"(detached)"}; head=$head; role=if([IO.Path]::GetFullPath($path) -eq [IO.Path]::GetFullPath($PrimaryPath)){"primary"}else{"linked"}; gitActive=$true } }
    return @($items)
}

function Get-StatusUnitFromTree {
    param($Tree, [string]$Roadmap)
    $branch = [string]$Tree.branch; $mode=$null; $slug=$null; $version=""
    if ($branch -match '^feature/(?:(?<version>v\d+\.\d+\.\d+)-)?(?<slug>\d{2}-[a-z0-9-]+)$') { $mode="Feature" }
    elseif ($branch -match '^milestone/(?:(?<version>v\d+\.\d+\.\d+)-)?(?<slug>[a-z0-9-]+)$') { $mode="Milestone" }
    else { return $null }
    $m=[regex]::Match($Roadmap,"(?m)^- \[(?<state>[ x-])\] $([regex]::Escape($slug))\b")
    $state=if($m.Success){switch($m.Groups.state.Value){' ' {'pending'} '-' {'ready'} 'x' {'done'}}}else{'unknown'}
    if ($state -eq 'done' -or $state -eq 'unknown') { return $null }
    [ordered]@{ unitId=$slug; mode=$mode; version=$version; branch=$branch; worktree=$Tree.path; head=$Tree.head; state=$state; lifecycle=if($state -eq 'ready'){'PR_OPEN_OR_READY'}else{'ACTIVE'}; source='git-worktree' }
}

function Get-StatusSnapshot {
    param([Parameter(Mandatory)][string]$Root)
    Push-Location $Root
    try {
        $branch=Invoke-StatusGit @('branch','--show-current'); if (!$branch){$branch='(detached)'}
        $head=Invoke-StatusGit @('rev-parse','HEAD')
        $primary=Invoke-StatusGit @('rev-parse','--show-toplevel')
        $trees=Get-StatusWorktrees (Invoke-StatusGit @('worktree','list','--porcelain')) $primary
        $roadmap=if(Test-Path ROADMAP.md){Get-Content ROADMAP.md -Raw -Encoding UTF8}else{""}
        $units=@($trees | Where-Object {$_.role -eq 'linked'} | ForEach-Object { Get-StatusUnitFromTree $_ $roadmap } | Where-Object { $null -ne $_ })
        # GitHub is optional for local reentry. CI/PR/release become explicitly
        # NOT AVAILABLE unless the caller provides an authenticated GH_TOKEN.
        $gh=if($env:GH_TOKEN){(Get-Command gh -ErrorAction SilentlyContinue).Source}else{$null}
        $repoInfo=Get-StatusGhJson $gh @('repo','view','--json','nameWithOwner')
        $repoName=if($repoInfo.Available){$repoInfo.Value.nameWithOwner}else{$null}
        $prInfo=Get-StatusGhJson $gh @('pr','list','--head',$branch,'--state','open','--json','number,title,url,headRefOid,baseRefName','--limit','10')
        $pr=if($prInfo.Available){@($prInfo.Value | Where-Object {$_.headRefOid -eq $head} | Select-Object -First 1)}else{@()}
        $prValue=if($pr.Count){$pr[0]}else{$null}
        $ciInfo=Get-StatusGhJson $gh @('run','list','--branch',$branch,'--commit',$head,'--limit','20','--json','name,status,conclusion,headSha,url,workflowName,createdAt')
        $runs=if($ciInfo.Available){@($ciInfo.Value | Where-Object {$_.headSha -eq $head})}else{@()}
        # Otros workflows (por ejemplo Guard develop branch) pueden fallar
        # sobre el mismo SHA sin ser el CI de producto. Sólo el workflow CI
        # determina el campo CI vigente del snapshot.
        $ciRuns=@($runs | Where-Object {$_.workflowName -eq 'CI'})
        $ci=if($ciRuns.Count){$ciRuns | Sort-Object createdAt -Descending | Select-Object -First 1}else{$null}
        $relInfo=Get-StatusGhJson $gh @('release','list','--limit','20','--json','tagName,name,publishedAt,isDraft,isPrerelease')
        $release=if($relInfo.Available){@($relInfo.Value | Where-Object {-not $_.isDraft -and -not $_.isPrerelease -and $_.publishedAt} | Sort-Object publishedAt -Descending | Select-Object -First 1)}else{@()}
        $releaseValue=if($release.Count){$release[0]}else{$null}
$tagText=Invoke-StatusGit @('tag','--sort=-version:refname')
$tags=@(($tagText -split "`r?`n") | Where-Object {$_ -match '^v\d+\.\d+\.\d+$'} | Select-Object -First 1)
$upstream=Invoke-StatusExternal 'git' @('rev-parse','--abbrev-ref','--symbolic-full-name','@{upstream}')
$remoteState=$null
if($upstream.Code -eq 0 -and -not [string]::IsNullOrWhiteSpace($upstream.Text) -and $upstream.Text -ne '@{upstream}') {
    $u=$upstream.Text
    $aheadResult=Invoke-StatusExternal 'git' @('rev-list','--left-right','--count','HEAD...@{upstream}')
    if($aheadResult.Code -eq 0){$remoteState=[ordered]@{upstream=$u; divergence=$aheadResult.Text}}
}
        $remote=Invoke-StatusExternal 'git' @('remote','get-url','origin')
        $working=if((Invoke-StatusGit @('status','--porcelain'))){'dirty'}else{'clean'}
        $version=Get-StatusVersion $Root $branch
        [ordered]@{ schemaVersion=2; generatedAt=[DateTime]::UtcNow.ToString('o'); repository=$repoName; version=$version; branch=$branch; head=$head; remote=if($remote.Code -eq 0){$remote.Text}else{$null}; remoteState=$remoteState; workingTree=$working; worktrees=$trees; activeUnits=$units; pullRequest=$prValue; ci=$ci; ciAvailable=$ciInfo.Available; ciReason=if($ciInfo.Available){if($ci){'HEAD_MATCH'}else{'NOT_RUN_FOR_HEAD'}}else{$ciInfo.Error}; latestRelease=$releaseValue; latestTag=if($tags.Count){$tags[0]}else{$null}; githubAvailable=($null -ne $gh); githubReason=if($prInfo.Available){$null}else{$prInfo.Error} }
    } finally { Pop-Location }
}

function Format-StatusValue { param($Value, [string]$Fallback='UNKNOWN / no disponible'); if($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)){$Fallback}else{[string]$Value} }

function New-StatusBlock { param([Parameter(Mandatory)]$Snapshot)
    $units=if(@($Snapshot.activeUnits).Count){(@($Snapshot.activeUnits)|ForEach-Object{"$($_.unitId)=$($_.state) [$($_.branch)]"}) -join '; '}else{'ninguna (no hay unidades ACTIVE)'}
    $pr=if($Snapshot.pullRequest){"#$($Snapshot.pullRequest.number) $($Snapshot.pullRequest.url) [OPEN, HEAD $($Snapshot.pullRequest.headRefOid)]"}else{'ninguna PR abierta para este HEAD'}
    $ci=if($Snapshot.ci){"$($Snapshot.ci.status)/$($Snapshot.ci.conclusion) @ $($Snapshot.ci.headSha)"}elseif($Snapshot.ciAvailable){'NOT RUN / no CI para este HEAD'}else{"NOT AVAILABLE / $($Snapshot.ciReason)"}
    $release=if($Snapshot.latestRelease){"$($Snapshot.latestRelease.tagName) (publicada $($Snapshot.latestRelease.publishedAt))"}else{'UNKNOWN / no release publicada verificable'}
    @('<!-- STATUS:AUTO:BEGIN -->','', '## Estado verificado automáticamente','',"- Actualizado: $($Snapshot.generatedAt)","- Versión de desarrollo: $(Format-StatusValue $Snapshot.version.value)","- Fuente de versión: $(Format-StatusValue $Snapshot.version.source)","- Rama: $($Snapshot.branch)","- HEAD: $($Snapshot.head)","- Remoto: $(Format-StatusValue $Snapshot.remote)","- Relación con remoto: $(if($Snapshot.remoteState){$Snapshot.remoteState.divergence}else{'sin upstream verificable'})","- Working tree: $($Snapshot.workingTree)","- Worktrees Git actuales: $(@($Snapshot.worktrees).Count)","- Unidades activas: $units","- PR vigente: $pr","- CI vigente: $ci","- Última release publicada: $release","- Último tag: $(Format-StatusValue $Snapshot.latestTag)",'','<!-- STATUS:AUTO:END -->') -join [Environment]::NewLine
}
