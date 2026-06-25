$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    $Python = 'python'
}

$Failures = New-Object System.Collections.Generic.List[string]
$Warnings = New-Object System.Collections.Generic.List[string]

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command,
        [switch]$WarnOnly
    )
    Write-Host ""
    Write-Host "== $Name =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        if ($WarnOnly) {
            $Warnings.Add("$Name returned exit code $LASTEXITCODE")
        }
        else {
            $Failures.Add("$Name returned exit code $LASTEXITCODE")
        }
    }
}

Push-Location $RepoRoot
try {
    Invoke-Step "Health check" { & $Python -m src.cli operational-health-check }
    Invoke-Step "Quick tests" { & $Python -m pytest -m "not slow" }
    Invoke-Step "Explain defaults" { & $Python -m src.cli explain-operational-defaults }
    Invoke-Step "Season sanity" { & $Python -m src.cli check-season-sanity --season-code 2526 --as-of-date 2026-05-25 --historical-mode }
    Invoke-Step "V1 CLI validation" { & $Python -m src.cli validate-v1 }

    $RawFiles = Get-ChildItem -Path 'data/raw/football-data' -Filter '*.csv' -ErrorAction SilentlyContinue
    if ($RawFiles.Count -gt 0) {
        Invoke-Step "Currentness check" {
            & $Python -m src.cli check-data-currentness --raw-dir data/raw/football-data --processed data/processed/operational_current_match_results.csv --as-of-date 2026-05-25 --season-code 2526 --leagues E0,E1,SP1,D1,I1,F1 --slate-type historical
        } -WarnOnly
        Invoke-Step "Run today local-only" {
            & $Python -m src.cli run-today --as-of-date 2026-05-25 --skip-download --max-matches 5
        } -WarnOnly
    }
    else {
        $Warnings.Add("No local Football-Data CSVs found; skipped currentness and run-today smoke.")
    }

    if (Test-Path 'outputs/runs') {
        Invoke-Step "Build viewer" { & $Python -m src.cli build-report-viewer --runs-root outputs/runs --output-dir outputs/viewer } -WarnOnly
    }
    else {
        $Warnings.Add("No outputs/runs folder found; skipped viewer build.")
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "== Final V1 Validation Summary =="
if ($Failures.Count -gt 0) {
    Write-Host "v1_script_status: fail"
    $Failures | ForEach-Object { Write-Host "- FAIL: $_" }
    exit 1
}
elseif ($Warnings.Count -gt 0) {
    Write-Host "v1_script_status: warn"
    $Warnings | ForEach-Object { Write-Host "- WARN: $_" }
    exit 0
}
else {
    Write-Host "v1_script_status: pass"
    exit 0
}
