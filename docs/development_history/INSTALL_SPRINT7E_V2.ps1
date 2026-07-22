$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 7E V2 - FINANCIAL ENGINE" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$required = @(
    ".\simulation\output\sales_v2\sales_events_v2.csv",
    ".\simulation\output\sales_v2\world_state_v2_day_180.json",
    ".\simulation\output\world\products.csv",
    ".\simulation\output\world\stores.csv"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 7E V2 dependency: $path"
    }
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\financial_v2" | Out-Null

python -c "from simulation.engines.financial_v2 import FinancialEngineV2; from simulation.application.financial_runner_v2 import FinancialRunnerV2; print('Sprint 7E V2 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7E V2 imports failed."
}

python -m unittest discover `
    -s ".\simulation\tests" `
    -p "test_financial_v2.py" `
    -v

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7E V2 tests failed."
}

Write-Host ""
Write-Host "SPRINT 7E V2 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7E_V2.ps1"
