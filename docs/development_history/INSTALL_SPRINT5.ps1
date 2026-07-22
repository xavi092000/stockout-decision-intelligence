$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 5 - ECONOMIC CALIBRATION" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not (Test-Path ".\reality_calibration")) {
    throw "Run this script from the stockout-prediction project root."
}

$dataDir = ".\reality_calibration\data\economics"
$outputDir = ".\reality_calibration\data\processed\economic_calibration"
$destination = Join-Path $dataDir "economic_indicators.csv"

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

if (-not (Test-Path $destination)) {
    Write-Host "Searching Downloads for a compatible economic CSV..." -ForegroundColor Yellow

    $candidates = Get-ChildItem "$HOME\Downloads" -File -Filter "*.csv" |
        Sort-Object LastWriteTime -Descending

    $selected = $null

    foreach ($candidate in $candidates) {
        try {
            $header = Get-Content $candidate.FullName -TotalCount 1 -ErrorAction Stop
            $headerLower = $header.ToLowerInvariant()

            $hasDate = (
                $headerLower.Contains("date") -or
                $headerLower.Contains("period") -or
                $headerLower.Contains("month")
            )
            $economicTokens = @(
                "inflation", "cpi", "consumer price",
                "fuel", "gasoline", "gas price",
                "retail sales", "retail trade"
            )
            $matches = 0
            foreach ($token in $economicTokens) {
                if ($headerLower.Contains($token)) {
                    $matches++
                }
            }

            if ($hasDate -and $matches -ge 2) {
                $selected = $candidate
                break
            }
        }
        catch {
            continue
        }
    }

    if ($null -eq $selected) {
        throw @"
No compatible economic CSV was found in Downloads.
Place a monthly CSV containing a date plus at least two of:
inflation/CPI, fuel/gasoline price, retail sales.
Then run INSTALL_SPRINT5.ps1 again.
"@
    }

    Copy-Item $selected.FullName $destination -Force
    Write-Host "Economic source selected: $($selected.Name)" -ForegroundColor Green
    Write-Host "Copied to: $destination" -ForegroundColor Green
}
else {
    Write-Host "Economic source already present: $destination" -ForegroundColor Green
}

python -c "import pandas, numpy; print('Python dependencies: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "pandas or numpy is unavailable in the active Python environment."
}

python -c "from reality_calibration.calibration.economic_calibration_engine import EconomicCalibrationEngine; print('Sprint 5 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 5 Python import validation failed."
}

Write-Host ""
Write-Host "SPRINT 5 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT5.ps1"
