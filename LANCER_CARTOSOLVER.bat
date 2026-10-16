@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 scripts\run.py %*
) else (
  python scripts\run.py %*
)
if errorlevel 1 (
  echo.
  echo Le lancement a echoue. Consultez l'erreur ci-dessus.
  pause
)
endlocal
