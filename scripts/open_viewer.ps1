param(
    [string]$Viewer = 'outputs/viewer/index.html'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    $Python = 'python'
}

Push-Location $RepoRoot
try {
    & $Python -m src.cli open-report-viewer --viewer $Viewer
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
