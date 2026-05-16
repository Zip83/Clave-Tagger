param(
    [string]$Python = "python",
    [string]$VenvPath = ".venv-maest"
)

$ErrorActionPreference = "Stop"

Set-Location -Path (Split-Path -Parent $PSScriptRoot)

Write-Host "ClaveTagger setup"
Write-Host "Project: $(Get-Location)"

if (-not (Test-Path -Path $VenvPath)) {
    Write-Host "Creating virtual environment: $VenvPath"
    & $Python -m venv $VenvPath
}
else {
    Write-Host "Virtual environment already exists: $VenvPath"
}

$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -Path $VenvPython)) {
    throw "Could not find $VenvPython"
}

Write-Host "Ensuring pip is installed..."
& $VenvPython -m ensurepip --upgrade

Write-Host "Upgrading pip..."
& $VenvPython -m pip install --upgrade pip

Write-Host "Installing requirements..."
& $VenvPython -m pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete."
Write-Host "Start GUI with: .\scripts\run_gui.ps1"
