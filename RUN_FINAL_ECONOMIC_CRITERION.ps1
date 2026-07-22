$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
Set-Location $projectRoot

& ".\.venv\Scripts\python.exe" -m simulation.benchmark_final_economic_criterion @args
exit $LASTEXITCODE
