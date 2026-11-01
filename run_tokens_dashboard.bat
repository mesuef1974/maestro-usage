@echo off
chcp 65001 >nul
title Tokens dashboard 8790
cd /d "%~dp0"

rem if the server is listening only open the browser, else start it minimized
netstat -ano | findstr /R /C:"127.0.0.1:8790 .*LISTENING" >nul
if errorlevel 1 (
    start "maestro_usage server" /min cmd /c "python src\serve.py --port 8790"
    timeout /t 3 /nobreak >nul
)

start "" "http://127.0.0.1:8790/"
exit /b 0
