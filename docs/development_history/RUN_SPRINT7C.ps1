$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 7C - SUPPLIER & ORDERS ENGINE" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path ".\simulation\output\supply") {
    Remove-Item `
        ".\simulation\output\supply\*" `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

python -m simulation.world.scripts.run_supply `
    --days 90 `
    --seed 42 `
    --initial-world ".\simulation\output\world\world_state_day_000.json" `
    --scenarios ".\simulation\output\scenarios\synthetic_scenarios_summary.csv" `
    --output-dir ".\simulation\output\supply"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7C supplier simulation failed."
}

Write-Host ""
Write-Host "SPRINT 7C EXECUTION: PASSED" -ForegroundColor Green
