$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " INSTALLING SPRINT 4 - WEATHER CALIBRATION" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

if (-not (Test-Path ".\reality_calibration")) {
    throw "Run this script from the stockout-prediction project root."
}

$dataDir = ".\reality_calibration\data\weather"
$outputDir = ".\reality_calibration\data\processed\weather_calibration"
$destination = Join-Path $dataDir "montreal_weather.csv"

New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

if (-not (Test-Path $destination)) {
    Write-Host "Searching Downloads for a compatible weather CSV..." -ForegroundColor Yellow

    $candidates = Get-ChildItem "$HOME\Downloads" -File -Filter "*.csv" |
        Sort-Object LastWriteTime -Descending

    $selected = $null

    foreach ($candidate in $candidates) {
        try {
            $header = Get-Content $candidate.FullName -TotalCount 1 -ErrorAction Stop
            $headerLower = $header.ToLowerInvariant()

            $hasDate = (
                $headerLower.Contains("date/time") -or
                $headerLower.Contains("date")
            )
            $hasTemperature = (
                $headerLower.Contains("mean temp") -or
                $headerLower.Contains("max temp") -or
                $headerLower.Contains("min temp") -or
                $headerLower.Contains("temperature")
            )

            if ($hasDate -and $hasTemperature) {
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
No compatible weather CSV was found in Downloads.
Download the Montreal daily historical weather CSV, leave it in Downloads,
then run INSTALL_SPRINT4.ps1 again.
"@
    }

    Copy-Item $selected.FullName $destination -Force
    Write-Host "Weather source selected: $($selected.Name)" -ForegroundColor Green
    Write-Host "Copied to: $destination" -ForegroundColor Green
}
else {
    Write-Host "Weather source already present: $destination" -ForegroundColor Green
}

python -c "import pandas, numpy; print('Python dependencies: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "pandas or numpy is unavailable in the active Python environment."
}

python -c "from reality_calibration.calibration import WeatherCalibrationEngine; print('Sprint 4 imports: PASSED')"
if ($LASTEXITCODE -ne 0) {
    throw "Sprint 4 Python import validation failed."
}

Write-Host ""
Write-Host "SPRINT 4 INSTALLATION: PASSED" -ForegroundColor Green
Write-Host "Run: powershell -ExecutionPolicy Bypass -File .\RUN_SPRINT4.ps1"
