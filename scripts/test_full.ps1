$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    $Python = 'python'
}

Write-Host "Running full test suite."
& $Python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
