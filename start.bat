@echo off
echo Starting AptaDeg...

:: Backend
start "AptaDeg Backend" cmd /k "cd /d %~dp0backend && python app.py"

:: Wait briefly then start frontend
timeout /t 2 /nobreak >nul
start "AptaDeg Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Backend  → http://localhost:5000
echo Frontend → http://localhost:3000
echo.
