@echo off
REM ============================================================================
REM Network Monitor - Start Server Script (Production)
REM Uses eventlet for production-grade WebSocket + WSGI
REM ============================================================================

cd /d "%~dp0"
echo [%date% %time%] Starting Network Monitor Server (Production)... >> server.log

REM Activate virtual environment and start production server
call .venv\Scripts\activate
python run_production.py >> server.log 2>&1
