@echo off
REM Double-clickable launcher for build.ps1.
REM -ExecutionPolicy Bypass applies to this one process only; it does not
REM change any machine setting.
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1" %*
echo.
pause
