@echo off
REM ============================================================================
REM Network Monitor - Remove Auto Start
REM Run this script AS ADMINISTRATOR to remove auto-start
REM ============================================================================

echo.
echo ============================================================
echo   Network Monitor - Remove Auto Start
echo ============================================================
echo.

REM Check for administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This script requires Administrator privileges!
    echo.
    echo Please right-click and select "Run as administrator"
    echo.
    pause
    exit /b 1
)

set "TASK_NAME=NetworkMonitor"

REM Delete the scheduled task
schtasks /delete /tn "%TASK_NAME%" /f

if %errorLevel% equ 0 (
    echo.
    echo ============================================================
    echo   [SUCCESS] Auto-start has been removed!
    echo ============================================================
    echo.
    echo The Network Monitor will no longer start automatically.
    echo.
) else (
    echo.
    echo [WARNING] Task "%TASK_NAME%" was not found or could not be deleted.
    echo It may have already been removed.
    echo.
)

pause
