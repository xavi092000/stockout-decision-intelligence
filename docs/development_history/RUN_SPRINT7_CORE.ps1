$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 7 CORE ARCHITECTURE REFACTOR" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

python -m simulation.scripts.migrate_world_state `
    --source ".\simulation\output\world\world_state_day_000.json" `
    --destination ".\simulation\output\core\world_state_v2_day_000.json" `
    --report ".\simulation\output\core\architecture_compatibility_report.json"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7 core migration failed."
}

Write-Host ""
Write-Host "SPRINT 7 CORE EXECUTION: PASSED" -ForegroundColor Green
