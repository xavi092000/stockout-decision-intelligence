$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " APPLYING SPRINT 4 HOTFIX 1" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

$target = ".\reality_calibration\loaders\weather_loader.py"

if (-not (Test-Path ".\reality_calibration\loaders")) {
    throw "Run this script from the stockout-prediction project root."
}

if (-not (Test-Path $target)) {
    throw "Sprint 4 weather_loader.py was not found."
}

python -c "from reality_calibration.loaders.weather_loader import WeatherDataLoader; print('Hotfix import: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 4 hotfix import validation failed."
}

Write-Host ""
Write-Host "SPRINT 4 HOTFIX: PASSED" -ForegroundColor Green
Write-Host "Now rerun: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT4.ps1"
