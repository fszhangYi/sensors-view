@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title sensors-view run :6008
call "%~dp0..\scripts\env_python.bat" || goto :fail

REM Live UI with login (password: see 启动与密码.txt / console)
set "SENSORS_VIEW_AUTH_DISABLED="

echo [sensors-view] run  http://127.0.0.1:6008/
"%PYTHON%" -m app.main --host 127.0.0.1 --port 6008
set "ERR=%ERRORLEVEL%"
goto :end

:fail
set "ERR=1"
:end
echo.
echo Exit code %ERR%. Press any key to close.
pause >nul
exit /b %ERR%
