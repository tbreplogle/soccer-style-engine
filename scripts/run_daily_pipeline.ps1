param(
    [string]$AsOfDate = (Get-Date -Format "yyyy-MM-dd"),
    [string]$SeasonCode = "2526",
    [string]$Leagues = "E0,E1,SP1,D1,I1,F1",
    [string]$CurrentnessPolicy = "fail-on-unsafe"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Host "Running operational health check..."
& $Python -m src.cli operational-health-check
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Checking data currentness..."
& $Python -m src.cli check-data-currentness --raw-dir data/raw/football-data --processed data/processed/operational_current_match_results.csv --as-of-date $AsOfDate --season-code $SeasonCode --leagues $Leagues
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running daily pipeline..."
& $Python -m src.cli run-daily-pipeline --as-of-date $AsOfDate --season-code $SeasonCode --leagues $Leagues --slate-type historical --max-matches 20 --skip-download --run-quick-audit --currentness-policy $CurrentnessPolicy
exit $LASTEXITCODE
