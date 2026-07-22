$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 8B V2 - ADAPTIVE POLICY" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path ".\simulation\output\adaptive_policy_v2") {
    Remove-Item `
        ".\simulation\output\adaptive_policy_v2\*" `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

python -m simulation.scripts.run_sprint8b_v2 `
    --days 365 `
    --seed 42 `
    --world ".\simulation\output\core\world_state_v2_day_000.json" `
    --scenarios ".\simulation\output\scenarios\synthetic_scenarios_summary.csv" `
    --output-dir ".\simulation\output\adaptive_policy_v2"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 8B V2 execution failed."
}

Write-Host ""
Write-Host "SPRINT 8B V2 EXECUTION: PASSED" -ForegroundColor Green
