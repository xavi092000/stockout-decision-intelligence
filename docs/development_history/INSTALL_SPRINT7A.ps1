$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 7A - WORLD STATE FOUNDATION" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
if (-not (Test-Path ".\simulation\output\scenarios\synthetic_scenarios_summary.csv")) { throw "Sprint 6 scenario summary is missing." }
$required = @("category_profiles.json","department_profiles.json","store_profiles.json","state_profiles.json")
foreach ($name in $required) { $p = ".\reality_calibration\data\processed\calibration\$name"; if (-not (Test-Path $p)) { throw "Missing calibration: $p" } }
New-Item -ItemType Directory -Force -Path ".\simulation\output\world" | Out-Null
python -c "import pandas; from simulation.world.world_state import build_world; print('Sprint 7A imports: PASSED')"
if ($LASTEXITCODE -ne 0) { throw "Sprint 7A import validation failed." }
Write-Host ""
Write-Host "SPRINT 7A INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT7A.ps1"
