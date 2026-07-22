$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 7C V2 - INTEGRATED ENGINES" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$required = @(
    ".\simulation\output\core\world_state_v2_day_000.json",
    ".\simulation\output\scenarios\synthetic_scenarios_summary.csv",
    ".\simulation\domain\models.py",
    ".\simulation\infrastructure\world_repository.py"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 7C V2 dependency: $path"
    }
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\domain_v2" | Out-Null

python -c "from simulation.engines import InventoryEngineV2, SupplierEngineV2; from simulation.application.simulation_runner_v2 import SimulationRunnerV2; print('Sprint 7C V2 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7C V2 imports failed."
}

python -m unittest discover `
    -s ".\simulation\tests" `
    -p "test_*v2.py" `
    -v

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7C V2 tests failed."
}

Write-Host ""
Write-Host "SPRINT 7C V2 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7C_V2.ps1"
