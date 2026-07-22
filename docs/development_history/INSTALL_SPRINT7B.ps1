$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 7B - DAILY INVENTORY ENGINE" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not (Test-Path ".\simulation")) {
    throw "Run this script from the stockout-prediction project root."
}

$required = @(
    ".\simulation\output\world\world_state_day_000.json",
    ".\simulation\output\scenarios\synthetic_scenarios_summary.csv"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 7B dependency: $path"
    }
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\inventory" | Out-Null

python -c "import pandas; from simulation.world.inventory_engine import DailyInventoryEngine; from simulation.world.inventory_runner import InventorySimulationRunner; print('Sprint 7B imports: PASSED')"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7B import validation failed."
}

Write-Host ""
Write-Host "SPRINT 7B INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7B.ps1"
