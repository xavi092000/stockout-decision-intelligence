$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 6 - SCENARIO ENGINE" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

python -m simulation.scripts.generate_scenarios `
    --days 365 `
    --seed 42 `
    --start-date "2027-01-01" `
    --demand-dir ".\reality_calibration\data\processed\calibration" `
    --weather-dir ".\reality_calibration\data\processed\weather_calibration" `
    --economic-dir ".\reality_calibration\data\processed\economic_calibration" `
    --output-dir ".\simulation\output\scenarios"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 6 scenario generation failed."
}

Write-Host ""
Write-Host "SPRINT 6 EXECUTION: PASSED" -ForegroundColor Green
