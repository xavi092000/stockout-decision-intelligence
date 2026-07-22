$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 7A - WORLD STATE FOUNDATION" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
python -m simulation.world.world_state --seed 42 --stores 10 --skus 100 --start-date "2027-01-01" --scenario-summary ".\simulation\output\scenarios\synthetic_scenarios_summary.csv" --demand-calibration-dir ".\reality_calibration\data\processed\calibration" --output-dir ".\simulation\output\world"
if ($LASTEXITCODE -ne 0) { throw "Sprint 7A execution failed." }
Write-Host ""
Write-Host "SPRINT 7A EXECUTION: PASSED" -ForegroundColor Green
