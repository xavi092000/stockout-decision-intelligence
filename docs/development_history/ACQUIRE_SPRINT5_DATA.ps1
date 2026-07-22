$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host " SPRINT 5 - OFFICIAL ECONOMIC DATA ACQUISITION" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan

if (-not (Test-Path ".\reality_calibration")) {
    throw "Run this script from the stockout-prediction project root."
}

$rawRoot = ".\reality_calibration\data\economics\raw_statcan"
$output = ".\reality_calibration\data\economics\economic_indicators.csv"

New-Item -ItemType Directory -Force -Path $rawRoot | Out-Null
New-Item -ItemType Directory -Force -Path (
    Split-Path $output -Parent
) | Out-Null

$tables = @(
    @{
        Name = "CPI"
        Id = "18100004"
        Url = "https://www150.statcan.gc.ca/n1/en/tbl/csv/18100004-eng.zip"
    },
    @{
        Name = "Gasoline"
        Id = "18100001"
        Url = "https://www150.statcan.gc.ca/n1/en/tbl/csv/18100001-eng.zip"
    },
    @{
        Name = "Retail"
        Id = "20100067"
        Url = "https://www150.statcan.gc.ca/n1/en/tbl/csv/20100067-eng.zip"
    }
)

foreach ($table in $tables) {
    $zipPath = Join-Path $rawRoot "$($table.Id)-eng.zip"
    $extractPath = Join-Path $rawRoot $table.Id

    Write-Host "Downloading $($table.Name) table..." -ForegroundColor Yellow
    Invoke-WebRequest `
        -Uri $table.Url `
        -OutFile $zipPath `
        -UseBasicParsing

    if (-not (Test-Path $zipPath)) {
        throw "Download failed for $($table.Name)."
    }

    New-Item -ItemType Directory -Force -Path $extractPath | Out-Null
    Expand-Archive `
        -Path $zipPath `
        -DestinationPath $extractPath `
        -Force

    Write-Host "$($table.Name): downloaded and extracted." -ForegroundColor Green
}

python -m reality_calibration.scripts.acquire_economic_data `
    --cpi-dir "$rawRoot\18100004" `
    --fuel-dir "$rawRoot\18100001" `
    --retail-dir "$rawRoot\20100067" `
    --output $output

if ($LASTEXITCODE -ne 0) {
    throw "Official economic data acquisition failed."
}

Write-Host ""
Write-Host "OFFICIAL ECONOMIC DATA: PASSED" -ForegroundColor Green
Write-Host "Now run INSTALL_SPRINT5.ps1, then RUN_SPRINT5.ps1."
