@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\test.ps1" %*
endlocal
