$ErrorActionPreference = "Stop"

Set-Location -Path (Split-Path -Parent $PSScriptRoot)

$VenvPython = ".venv-maest\Scripts\python.exe"
if (-not (Test-Path -Path $VenvPython)) {
    Write-Host "Virtual environment not found. Running setup first..."
    & powershell -ExecutionPolicy Bypass -File ".\scripts\setup.ps1"
}

& $VenvPython -m unittest discover -s tests -v
