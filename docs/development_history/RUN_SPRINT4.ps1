$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 4 - WEATHER CALIBRATION" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

python -m reality_calibration.scripts.build_weather_calibration `
    --source ".\reality_calibration\data\weather\montreal_weather.csv" `
    --output-dir ".\reality_calibration\data\processed\weather_calibration"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 4 weather calibration failed."
}

Write-Host ""
Write-Host "SPRINT 4 EXECUTION: PASSED" -ForegroundColor Green
