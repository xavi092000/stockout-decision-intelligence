$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python environment not found: $python"
}

& $python -W ignore::sklearn.exceptions.InconsistentVersionWarning `
    -m simulation.benchmark_service_ceiling_fast `
    --seeds 131 132 133 134 135 `
    --workers 5 `
    --days-cover 45 `
    --service-target 0.95

exit $LASTEXITCODE
