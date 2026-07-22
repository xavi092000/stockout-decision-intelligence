$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 3 - DEMAND CALIBRATION ENGINE" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not (Test-Path ".\reality_calibration")) {
    throw "Run this script from the stockout-prediction project root."
}

$requiredDirs = @(
    ".\reality_calibration\calibration",
    ".\reality_calibration\profiles",
    ".\reality_calibration\validation",
    ".\reality_calibration\scripts",
    ".\reality_calibration\data\processed\demand",
    ".\reality_calibration\data\processed\calibration"
)

foreach ($dir in $requiredDirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$requiredSprint2Outputs = @(
    "series_demand_profiles.csv",
    "category_demand_profiles.csv",
    "department_demand_profiles.csv",
    "store_demand_profiles.csv",
    "state_demand_profiles.csv",
    "weekday_demand_profile.csv",
    "demand_analysis_summary.json"
)

foreach ($file in $requiredSprint2Outputs) {
    $path = Join-Path ".\reality_calibration\data\processed\demand" $file
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 2 output: $path. Run RUN_SPRINT2.ps1 first."
    }
}

python -c "import pandas, numpy; print('Python dependencies: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "pandas or numpy is unavailable in the active Python environment."
}

python -c "from reality_calibration.calibration import DemandCalibrationEngine; print('Sprint 3 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 3 Python import validation failed."
}

Write-Host ""
Write-Host "SPRINT 3 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT3.ps1"
