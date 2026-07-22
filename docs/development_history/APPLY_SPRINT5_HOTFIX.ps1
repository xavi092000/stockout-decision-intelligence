$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " APPLYING SPRINT 5 HOTFIX - FUEL SERIES" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

if (-not (Test-Path ".\reality_calibration\loaders\economic_loader.py")) {
    throw "Run this script from the stockout-prediction project root."
}

python -c "from reality_calibration.loaders.economic_loader import EconomicDataLoader; import pathlib; f=EconomicDataLoader(pathlib.Path('reality_calibration/data/economics/economic_indicators.csv')).read_normalized(); assert f['fuel_price'].notna().any(); assert f['retail_sales'].notna().any(); assert f['inflation'].notna().any(); print('Three economic series detected: PASSED')"

if ($LASTEXITCODE -ne 0) {
    throw "Sprint 5 hotfix validation failed."
}

Write-Host ""
Write-Host "SPRINT 5 HOTFIX: PASSED" -ForegroundColor Green
Write-Host "Now rerun RUN_SPRINT5.ps1."
