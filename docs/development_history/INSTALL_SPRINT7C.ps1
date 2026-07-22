$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 7C - SUPPLIER & ORDERS ENGINE" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not (Test-Path ".\simulation")) {
    throw "Run this script from the stockout-prediction project root."
}

$required = @(
    ".\simulation\output\world\world_state_day_000.json",
    ".\simulation\output\scenarios\synthetic_scenarios_summary.csv",
    ".\simulation\world\inventory_engine.py"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 7C dependency: $path"
    }
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\supply" | Out-Null

python -c "import pandas; from simulation.world.supplier_engine import SupplierOrderEngine; from simulation.world.supply_runner import SupplySimulationRunner; print('Sprint 7C imports: PASSED')"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7C import validation failed."
}

Write-Host ""
Write-Host "SPRINT 7C INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7C.ps1"
