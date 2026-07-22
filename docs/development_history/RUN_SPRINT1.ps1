$ErrorActionPreference = "Stop"

Write-Host "Running M5 Foundation audit..." -ForegroundColor Cyan

python -m reality_calibration.scripts.analyze_m5 `
  --data-dir ".\reality_calibration\data\m5"

if ($LASTEXITCODE -ne 0) {
    throw "M5 audit failed."
}

Write-Host ""
Write-Host "M5 Foundation audit completed successfully." -ForegroundColor Green
