$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 7D V2 - SALES & STOCKOUT ENGINE" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path ".\simulation\output\sales_v2") {
    Remove-Item `
        ".\simulation\output\sales_v2\*" `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

python -m simulation.scripts.run_sprint7d_v2 `
    --days 180 `
    --seed 42 `
    --world ".\simulation\output\core\world_state_v2_day_000.json" `
    --scenarios ".\simulation\output\scenarios\synthetic_scenarios_summary.csv" `
    --output-dir ".\simulation\output\sales_v2"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7D V2 execution failed."
}

Write-Host ""
Write-Host "SPRINT 7D V2 EXECUTION: PASSED" -ForegroundColor Green
