param(
    [string]$Marker = 'not slow'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    $Python = 'python'
}

Write-Host "Running quick tests with marker: $Marker"
& $Python -m pytest -m $Marker
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
