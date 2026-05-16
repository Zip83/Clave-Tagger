@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\run_gui.ps1" %*
endlocal
