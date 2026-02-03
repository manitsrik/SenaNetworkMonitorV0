@echo off
REM ============================================================================
REM Network Monitor - Install Auto Start at Windows Startup
REM Run this script AS ADMINISTRATOR to set up auto-start
REM ============================================================================

echo.
echo ============================================================
echo   Network Monitor - Auto Start Installation
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

REM Get the directory of this script
set "SCRIPT_DIR=%~dp0"
set "TASK_NAME=NetworkMonitor"

echo Script Directory: %SCRIPT_DIR%
echo.

REM Check if start_server.bat exists
if not exist "%SCRIPT_DIR%start_server.bat" (
    echo [ERROR] start_server.bat not found!
    echo Please ensure start_server.bat is in the same directory.
    pause
    exit /b 1
)

REM Delete existing task if it exists
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

REM Create scheduled task to run at system startup (before login)
REM Using short path format to avoid space issues
echo Creating scheduled task...
for %%I in ("%SCRIPT_DIR%start_server.bat") do set "SHORT_PATH=%%~sI"
echo Start Script: %SHORT_PATH%

schtasks /create /tn "%TASK_NAME%" /tr "%SHORT_PATH%" /sc onstart /ru SYSTEM /rl highest /f

if %errorLevel% equ 0 (
    echo.
    echo ============================================================
    echo   [SUCCESS] Auto-start has been configured!
    echo ============================================================
    echo.
    echo Task Name: %TASK_NAME%
    echo Trigger: At system startup (before login)
    echo.
    echo The Network Monitor server will now start automatically
    echo when Windows starts (before login).
    echo.
    echo To manage this task:
    echo   - Open Task Scheduler (taskschd.msc)
    echo   - Look for "%TASK_NAME%" in the Task Scheduler Library
    echo.
    echo To remove auto-start, run: uninstall_autostart.bat
    echo.
) else (
    echo.
    echo [ERROR] Failed to create scheduled task!
    echo Error code: %errorLevel%
    echo.
)

pause
