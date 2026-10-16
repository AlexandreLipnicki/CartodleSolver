@echo off
cd /d "%~dp0"
.venv\Scripts\python.exe -m pytest backend\tests -q
if errorlevel 1 goto error
call npm --prefix frontend run build
if errorlevel 1 goto error
exit /b 0
:error
pause
exit /b 1
