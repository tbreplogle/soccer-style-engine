param(
    [string]$AsOfDate = '',
    [string]$Leagues = 'E0,E1,SP1,D1,I1,F1',
    [int]$MaxMatches = 20,
    [switch]$SkipDownload,
    [switch]$Download,
    [switch]$IncludeInternational,
    [switch]$RunProfileComparison
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    $Python = 'python'
}

if (-not $AsOfDate) {
    $AsOfDate = Get-Date -Format 'yyyy-MM-dd'
}

Push-Location $RepoRoot
try {
    Write-Host "Running operational health check."
    & $Python -m src.cli operational-health-check
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    $Args = @(
        '-m', 'src.cli', 'run-today',
        '--as-of-date', $AsOfDate,
        '--leagues', $Leagues,
        '--max-matches', $MaxMatches
    )
    if ($SkipDownload -or -not $Download) { $Args += '--skip-download' }
    if ($IncludeInternational) { $Args += '--include-international' }
    if ($RunProfileComparison) { $Args += '--run-profile-comparison' }

    Write-Host "Running daily workflow for $AsOfDate."
    & $Python @Args
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Viewer path: $(Join-Path $RepoRoot 'outputs\viewer\index.html')"
}
finally {
    Pop-Location
}
