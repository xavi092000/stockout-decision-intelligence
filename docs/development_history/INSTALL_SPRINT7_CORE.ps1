$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 7 CORE ARCHITECTURE REFACTOR" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

if (-not (Test-Path ".\simulation")) {
    throw "Run this script from the stockout-prediction project root."
}

$sourceWorld = ".\simulation\output\world\world_state_day_000.json"
if (-not (Test-Path $sourceWorld)) {
    throw "Missing source world state: $sourceWorld"
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\core" | Out-Null

python -c "from simulation.domain import WorldState, Supplier, SCHEMA_VERSION; from simulation.infrastructure import JsonWorldRepository; print('Unified domain imports: PASSED'); print('Target schema:', SCHEMA_VERSION)"
if ($LASTEXITCODE -ne 0) {
    throw "Unified domain import validation failed."
}

python -m unittest discover `
    -s ".\simulation\tests" `
    -p "test_*.py" `
    -v

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7 core unit tests failed."
}

Write-Host ""
Write-Host "SPRINT 7 CORE INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7_CORE.ps1"
