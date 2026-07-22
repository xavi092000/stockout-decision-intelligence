$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 8B V2 - ADAPTIVE POLICY" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$required = @(
    ".\simulation\output\core\world_state_v2_day_000.json",
    ".\simulation\output\scenarios\synthetic_scenarios_summary.csv",
    ".\simulation\decision\policies_v2.py",
    ".\simulation\engines\sales_v2.py",
    ".\simulation\engines\supplier_v2.py",
    ".\simulation\engines\economic_sanity_v2.py"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Missing Sprint 8B V2 dependency: $path"
    }
}

New-Item `
    -ItemType Directory `
    -Force `
    -Path ".\simulation\output\adaptive_policy_v2" | Out-Null

python -c "from simulation.decision.adaptive_policy_v2 import AdaptivePolicyEngineV2; from simulation.application.adaptive_runner_v2 import AdaptiveSimulationRunnerV2; print('Sprint 8B V2 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 8B V2 imports failed."
}

python -m unittest discover `
    -s ".\simulation\tests" `
    -p "test_adaptive_policy_v2.py" `
    -v

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 8B V2 tests failed."
}

Write-Host ""
Write-Host "SPRINT 8B V2 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT8B_V2.ps1"
