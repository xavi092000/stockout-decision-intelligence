$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " RUNNING SPRINT 7F V2 - ECONOMIC SANITY" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host ""

if (Test-Path ".\simulation\output\economic_sanity_v2") {
    Remove-Item `
        ".\simulation\output\economic_sanity_v2\*" `
        -Recurse `
        -Force `
        -ErrorAction SilentlyContinue
}

python -m simulation.scripts.run_sprint7f_v2 `
    --financial-summary ".\simulation\output\financial_v2\financial_summary_v2.json" `
    --sales-metrics ".\simulation\output\sales_v2\sales_daily_metrics_v2.csv" `
    --output-dir ".\simulation\output\economic_sanity_v2"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 7F V2 execution failed."
}

Write-Host ""
Write-Host "SPRINT 7F V2 EXECUTION: PASSED" -ForegroundColor Green
