@echo off
setlocal

set "LAUNCHER=%~dp0run-local.ps1"
if not exist "%LAUNCHER%" (
    echo Could not find run-local.ps1 beside this batch file.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%LAUNCHER%"
if errorlevel 1 (
    echo The POS stopped because startup failed.
    pause
)
