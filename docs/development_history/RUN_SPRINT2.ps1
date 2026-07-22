$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 2 - DEMAND INTELLIGENCE" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "This analysis processes more than 58 million sales observations."
Write-Host ""

python -m reality_calibration.scripts.analyze_demand `
    --data-dir ".\reality_calibration\data\m5" `
    --output-dir ".\reality_calibration\data\processed\demand" `
    --chunksize 250

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 2 demand analysis failed."
}

Write-Host ""
Write-Host "SPRINT 2 EXECUTION: PASSED" -ForegroundColor Green
