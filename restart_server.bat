@echo off
echo Stopping Flask server...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *app.py*" 2>nul
timeout /t 2 /nobreak >nul

echo Starting Flask server...
call .venv\Scripts\activate
start "Network Monitor" python app.py

echo.
echo Server is starting...
echo Dashboard: http://localhost:5000
echo.
