# PowerShell script to run Local Search experiment via the current src/ layout
$ErrorActionPreference = "Stop"

# Set encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Get script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Current directory: $scriptDir" -ForegroundColor Green
Write-Host "Legacy wrapper notice: forwarding to src/test/test_FCP_LS.py" -ForegroundColor Yellow
Write-Host "Preferred current workflow: activate .venv and run python src/test/test_FCP_LS.py" -ForegroundColor Yellow

# Prefer a local Windows venv when present; otherwise fall back to PATH Python
$pythonCmd = $null
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonCmd = $venvPython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $pythonCmd = "python3"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py"
} else {
    Write-Host "Error: Python not found in PATH" -ForegroundColor Red
    Write-Host "Please ensure Python is installed or create a local .venv" -ForegroundColor Yellow
    exit 1
}

Write-Host "Using Python: $pythonCmd" -ForegroundColor Cyan

# Run the experiment
& $pythonCmd "src/test/test_FCP_LS.py"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nExperiment completed successfully!" -ForegroundColor Green
} else {
    Write-Host "`nExperiment failed with exit code: $LASTEXITCODE" -ForegroundColor Red
}



