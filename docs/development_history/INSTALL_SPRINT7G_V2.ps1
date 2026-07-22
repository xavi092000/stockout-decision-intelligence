$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 7G V2 - 365-DAY ORCHESTRATOR" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$required = @(
    ".\simulation\output\core\world_state_v2_day_000.json",
    ".\simulation\output\scenarios\synthetic_scenarios_summary.csv",
    ".\simulation\engines\sales_v2.py",
    ".\simulation\engines\supplier_v2.py",
    ".\simulation\engines\economic_sanity_v2.py"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 7G V2 dependency: $path"
    }
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\orchestrator_v2" | Out-Null

python -c "from simulation.application.orchestrator_v2 import SimulationOrchestratorV2; print('Sprint 7G V2 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7G V2 imports failed."
}

python -m unittest discover `
    -s ".\simulation\tests" `
    -p "test_orchestrator_v2.py" `
    -v

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7G V2 tests failed."
}

Write-Host ""
Write-Host "SPRINT 7G V2 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7G_V2.ps1"
