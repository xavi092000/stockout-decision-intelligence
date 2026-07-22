$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 5 - ECONOMIC CALIBRATION" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

python -m reality_calibration.scripts.build_economic_calibration `
    --source ".\reality_calibration\data\economics\economic_indicators.csv" `
    --output-dir ".\reality_calibration\data\processed\economic_calibration"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 5 economic calibration failed."
}

Write-Host ""
Write-Host "SPRINT 5 EXECUTION: PASSED" -ForegroundColor Green
