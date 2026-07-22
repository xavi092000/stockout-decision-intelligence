$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 7B - DAILY INVENTORY ENGINE" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path ".\simulation\output\inventory") {
    Remove-Item `
        ".\simulation\output\inventory\*" `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

python -m simulation.world.scripts.run_inventory `
    --days 30 `
    --seed 42 `
    --initial-world ".\simulation\output\world\world_state_day_000.json" `
    --scenarios ".\simulation\output\scenarios\synthetic_scenarios_summary.csv" `
    --output-dir ".\simulation\output\inventory"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7B inventory simulation failed."
}

Write-Host ""
Write-Host "SPRINT 7B EXECUTION: PASSED" -ForegroundColor Green
