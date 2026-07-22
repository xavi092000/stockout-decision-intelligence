$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Set-Location $ProjectRoot

if (-not (Test-Path $PythonExe)) {
    throw "Python virtual environment not found: $PythonExe"
}

& $PythonExe -m simulation.validate_synthetic_generation

if ($LASTEXITCODE -ne 0) {
    throw "Synthetic generation validation failed."
}
