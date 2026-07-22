$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 7D V2 - SALES & STOCKOUT ENGINE" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$required = @(
    ".\simulation\output\core\world_state_v2_day_000.json",
    ".\simulation\output\scenarios\synthetic_scenarios_summary.csv",
    ".\simulation\domain\models.py",
    ".\simulation\engines\supplier_v2.py"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 7D V2 dependency: $path"
    }
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\sales_v2" | Out-Null

python -c "from simulation.engines.sales_v2 import SalesEngineV2; from simulation.application.sales_runner_v2 import SalesSimulationRunnerV2; print('Sprint 7D V2 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7D V2 imports failed."
}

python -m unittest discover `
    -s ".\simulation\tests" `
    -p "test_sales_v2.py" `
    -v

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7D V2 tests failed."
}

Write-Host ""
Write-Host "SPRINT 7D V2 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7D_V2.ps1"
