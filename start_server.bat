@echo off
REM ============================================================================
REM Network Monitor - Start Server Script
REM This script starts the Flask server silently in the background
REM ============================================================================

cd /d "%~dp0"
echo [%date% %time%] Starting Network Monitor Server... >> server.log

REM Activate virtual environment and start server
call .venv\Scripts\activate
python app.py >> server.log 2>&1
