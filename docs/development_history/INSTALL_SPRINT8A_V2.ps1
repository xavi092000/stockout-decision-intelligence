$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 8A V2 - POLICY COMPARISON" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$required = @(
    ".\simulation\output\core\world_state_v2_day_000.json",
    ".\simulation\output\scenarios\synthetic_scenarios_summary.csv",
    ".\simulation\application\orchestrator_v2.py",
    ".\simulation\engines\economic_sanity_v2.py"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 8A V2 dependency: $path"
    }
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\policy_comparison_v2" | Out-Null

python -c "from simulation.decision import POLICIES, InventoryPolicyApplier; from simulation.application.policy_comparison_runner_v2 import PolicyComparisonRunnerV2; print('Sprint 8A V2 imports: PASSED'); print('Policies:', ', '.join(POLICIES))"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 8A V2 imports failed."
}

python -m unittest discover `
    -s ".\simulation\tests" `
    -p "test_policy_comparison_v2.py" `
    -v

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 8A V2 tests failed."
}

Write-Host ""
Write-Host "SPRINT 8A V2 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT8A_V2.ps1"
