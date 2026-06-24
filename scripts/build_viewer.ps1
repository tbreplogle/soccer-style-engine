param(
    [string]$RunsRoot = 'outputs/runs',
    [string]$OutputDir = 'outputs/viewer'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    $Python = 'python'
}

Push-Location $RepoRoot
try {
    & $Python -m src.cli build-report-viewer --runs-root $RunsRoot --output-dir $OutputDir
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
