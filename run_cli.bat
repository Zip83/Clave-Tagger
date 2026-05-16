@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\run_cli.ps1" %*
endlocal
