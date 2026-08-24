@echo off
REM Tiny task runner, so you never type the full venv path.
REM JAVA: this is your mvn goals / npm scripts.
REM
REM   dev            start the API with auto-reload
REM   dev test       run the test suite
REM   dev admin ...  create or promote an admin
REM   dev demo       walk the whole auth flow
REM   dev install    install dependencies
REM   dev shell      python REPL with the app importable
REM
REM A .cmd file (not .ps1) on purpose: PowerShell's execution policy blocks
REM unsigned .ps1 scripts by default, and this has no such problem.

setlocal
cd /d "%~dp0"
set PY=%~dp0venv\Scripts\python.exe

if not exist "%PY%" (
    echo [dev] No venv found at %PY%
    echo [dev] Create it with:  python -m venv venv
    exit /b 1
)

REM Everything after the first word, so args pass through to the sub-command.
set ARGS=%*
if not "%~1"=="" call set ARGS=%%ARGS:*%1=%%

if "%~1"==""        goto :run
if /i "%~1"=="run"  goto :run
if /i "%~1"=="dev"  goto :run
if /i "%~1"=="test" goto :test
if /i "%~1"=="admin" goto :admin
if /i "%~1"=="demo" goto :demo
if /i "%~1"=="install" goto :install
if /i "%~1"=="shell" goto :shell

echo [dev] Unknown command: %~1
echo [dev] Try: run ^| test ^| admin ^| demo ^| install ^| shell
exit /b 1

:run
echo [dev] http://127.0.0.1:8000/docs   (Ctrl+C to stop)
"%PY%" -m uvicorn app.main:app --reload %ARGS%
goto :eof

:test
"%PY%" -m pytest -q %ARGS%
goto :eof

:admin
"%PY%" scripts\create_admin.py %ARGS%
goto :eof

:demo
"%PY%" scripts\demo_auth.py %ARGS%
goto :eof

:install
"%PY%" -m pip install -r requirements.txt
goto :eof

:shell
"%PY%"
goto :eof
