@echo off
setlocal
cd /d "%~dp0"

REM The PowerShell script requests Administrator privileges when required.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_server.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Restart failed with exit code %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%
