@echo off
rem تشغيل لوحة التوكنز: يبدأ الخادم إن لم يكن يردّ ثم يفتح المتصفح.
rem الاستعمال: run_tokens_dashboard.bat [المنفذ] [noopen]   (الافتراضي 8790، وnoopen يمنع فتح المتصفح)
rem يُستدعى عند تسجيل الدخول من مجلد Startup عبر TokensDashboard.bat، ويكتب أثره في data\startup_bat.log
chcp 65001 >nul
setlocal EnableDelayedExpansion
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8790"
set "ROOT=%~dp0"
cd /d "%ROOT%"
if not exist "data" mkdir "data"
set "LOG=data\startup_bat.log"

rem بايثون بمسار كامل (PATH عند تسجيل الدخول قد يختلف عن الصدفة)، وpythonw بلا نافذة تُغلق بالخطأ
set "PY=%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
if not exist "%PY%" set "PY=pythonw.exe"

rem الكشف بطلب HTTP فعلي (netstat/findstr غير موثوق: كلمة الحالة قد تغيب أو تتأخر)
curl.exe -s -o NUL --max-time 2 "http://127.0.0.1:%PORT%/"
if errorlevel 1 (
    >> "%LOG%" echo !date! !time! port=%PORT% not responding; starting "%PY%"
    start "" "%PY%" src\serve.py --port %PORT%
    timeout /t 3 /nobreak >nul
    curl.exe -s -o NUL --max-time 2 "http://127.0.0.1:%PORT%/"
    if errorlevel 1 (
        >> "%LOG%" echo !date! !time! port=%PORT% still not responding after start
    ) else (
        >> "%LOG%" echo !date! !time! port=%PORT% up
    )
) else (
    >> "%LOG%" echo !date! !time! port=%PORT% already up
)

if /i not "%~2"=="noopen" start "" "http://127.0.0.1:%PORT%/"
exit /b 0
