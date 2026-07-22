$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 6 - SCENARIO ENGINE" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not (Test-Path ".\reality_calibration")) {
    throw "Run this script from the stockout-prediction project root."
}

$required = @(
    ".\reality_calibration\data\processed\calibration\global_profile.json",
    ".\reality_calibration\data\processed\calibration\category_profiles.json",
    ".\reality_calibration\data\processed\calibration\department_profiles.json",
    ".\reality_calibration\data\processed\calibration\store_profiles.json",
    ".\reality_calibration\data\processed\calibration\state_profiles.json",
    ".\reality_calibration\data\processed\calibration\demand_class_profiles.json",
    ".\reality_calibration\data\processed\calibration\weekday_profiles.json",
    ".\reality_calibration\data\processed\weather_calibration\weather_calibration_profile.json",
    ".\reality_calibration\data\processed\economic_calibration\economic_calibration_profile.json"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing calibration dependency: $path"
    }
}

New-Item -ItemType Directory -Force -Path ".\simulation\output\scenarios" | Out-Null

python -c "import pandas; from simulation import ScenarioEngine, CalibrationRepository; print('Sprint 6 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 6 Python import validation failed."
}

Write-Host ""
Write-Host "SPRINT 6 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT6.ps1"
