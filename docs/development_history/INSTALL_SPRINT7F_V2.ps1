$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 7F V2 - ECONOMIC SANITY" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$required = @(
    ".\simulation\output\financial_v2\financial_summary_v2.json",
    ".\simulation\output\sales_v2\sales_daily_metrics_v2.csv"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 7F V2 dependency: $path"
    }
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\economic_sanity_v2" | Out-Null

python -c "from simulation.engines.economic_sanity_v2 import EconomicSanityEngineV2; from simulation.application.economic_sanity_runner_v2 import EconomicSanityRunnerV2; print('Sprint 7F V2 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7F V2 imports failed."
}

python -m unittest discover `
    -s ".\simulation\tests" `
    -p "test_economic_sanity_v2.py" `
    -v

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7F V2 tests failed."
}

Write-Host ""
Write-Host "SPRINT 7F V2 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7F_V2.ps1"
