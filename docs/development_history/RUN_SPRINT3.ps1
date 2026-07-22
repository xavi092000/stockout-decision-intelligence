$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 3 - DEMAND CALIBRATION ENGINE" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

python -m reality_calibration.scripts.build_demand_calibration `
    --demand-dir ".\reality_calibration\data\processed\demand" `
    --output-dir ".\reality_calibration\data\processed\calibration"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 3 calibration build failed."
}

Write-Host ""
Write-Host "SPRINT 3 EXECUTION: PASSED" -ForegroundColor Green
