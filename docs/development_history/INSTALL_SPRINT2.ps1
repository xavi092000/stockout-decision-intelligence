$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 2 - DEMAND INTELLIGENCE" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

if (-not (Test-Path ".\reality_calibration")) {
    throw "Run this script from the stockout-prediction project root."
}

$requiredDirs = @(
    ".\reality_calibration\analyzers",
    ".\reality_calibration\profiles",
    ".\reality_calibration\validation",
    ".\reality_calibration\scripts",
    ".\reality_calibration\data\m5",
    ".\reality_calibration\data\processed\demand"
)

foreach ($dir in $requiredDirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$m5Files = @(
    "sales_train_validation.csv",
    "calendar(1).csv",
    "sell_prices.csv"
)

foreach ($file in $m5Files) {
    $destination = Join-Path ".\reality_calibration\data\m5" $file
    if (-not (Test-Path $destination)) {
        $downloadName = $file
        if ($file -eq "calendar(1).csv") {
            $downloadName = "calendar.csv"
        }
        $source = Join-Path "$HOME\Downloads" $downloadName
        if (Test-Path $source) {
            Copy-Item $source $destination -Force
            Write-Host "Copied $downloadName from Downloads." -ForegroundColor Yellow
        }
        else {
            throw "Missing dataset: $destination and $source"
        }
    }
}

python -c "import pandas, numpy; print('Python dependencies: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "pandas or numpy is unavailable in the active Python environment."
}

Write-Host ""
Write-Host "SPRINT 2 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT2.ps1"
