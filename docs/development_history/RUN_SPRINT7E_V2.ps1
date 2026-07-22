$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 7E V2 - FINANCIAL ENGINE" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path ".\simulation\output\financial_v2") {
    Remove-Item `
        ".\simulation\output\financial_v2\*" `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

python -m simulation.scripts.run_sprint7e_v2 `
    --days 180 `
    --sales-dir ".\simulation\output\sales_v2" `
    --world-dir ".\simulation\output\world" `
    --output-dir ".\simulation\output\financial_v2"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7E V2 execution failed."
}

Write-Host ""
Write-Host "SPRINT 7E V2 EXECUTION: PASSED" -ForegroundColor Green
