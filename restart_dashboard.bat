@echo off
rem إعادة تشغيل خادم ميزان (127.0.0.1:8790): يوقف العملية التي تسمع على المنفذ ثم يشغّل run_tokens_dashboard.bat
chcp 65001 >nul
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8790"
cd /d "%~dp0"
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
timeout /t 2 /nobreak >nul
call run_tokens_dashboard.bat %PORT%
