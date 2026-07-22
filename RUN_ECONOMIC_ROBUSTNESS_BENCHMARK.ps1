param(
    [int]$StartSeed = 101,
    [int]$Episodes = 30,
    [int]$Workers = 6
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ModelPath = Join-Path $ProjectRoot "artifacts\policy_training\decision_tree.joblib"
$OutputDir = Join-Path $ProjectRoot "artifacts\policy_training\economic_robustness"

if (-not (Test-Path $PythonExe)) {
    throw "Python virtual environment not found: $PythonExe"
}
if (-not (Test-Path $ModelPath)) {
    throw "Policy model not found: $ModelPath"
}
if ($Episodes -lt 30) {
    throw "Economic acceptance requires at least 30 episodes."
}

Set-Location $ProjectRoot

& $PythonExe -m simulation.benchmark_ml_policy_robust `
    --start-seed $StartSeed `
    --episodes $Episodes `
    --workers $Workers `
    --model-path $ModelPath `
    --output-dir $OutputDir

if ($LASTEXITCODE -ne 0) {
    throw "Economic robustness benchmark failed."
}

$SummaryPath = Join-Path $OutputDir "summary.json"
if (-not (Test-Path $SummaryPath)) {
    throw "Benchmark summary not found: $SummaryPath"
}

$Summary = Get-Content $SummaryPath -Raw | ConvertFrom-Json
$Accepted = [bool]$Summary.economic_robustness.accepted

Write-Host ""
if ($Accepted) {
    Write-Host "Economic robustness: PASS" -ForegroundColor Green
} else {
    Write-Host "Economic robustness: FAIL" -ForegroundColor Red
    Write-Host ("Failed scenarios: " + ($Summary.economic_robustness.failed_scenarios -join ", "))
}
Write-Host "Report: $SummaryPath"

if (-not $Accepted) {
    exit 2
}
