$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 7C V2 - INTEGRATED ENGINES" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path ".\simulation\output\domain_v2") {
    Remove-Item `
        ".\simulation\output\domain_v2\*" `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

python -m simulation.scripts.run_sprint7c_v2 `
    --days 90 `
    --seed 42 `
    --world ".\simulation\output\core\world_state_v2_day_000.json" `
    --scenarios ".\simulation\output\scenarios\synthetic_scenarios_summary.csv" `
    --output-dir ".\simulation\output\domain_v2"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7C V2 execution failed."
}

Write-Host ""
Write-Host "SPRINT 7C V2 EXECUTION: PASSED" -ForegroundColor Green
