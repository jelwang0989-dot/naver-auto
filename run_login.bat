@echo off
setlocal

:: Switch to script directory
cd /d "%~dp0"

:: Set window title (ASCII safe)
title AI Partner Auto Login

echo ========================================================
echo   AI Partner Auto Login
echo ========================================================
echo.

:: Detect Python executable (python or py)
set "PY_CMD="
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=python"
) else (
    where py >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        set "PY_CMD=py"
    )
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python and check 'Add python.exe to PATH'.
    echo.
    pause
    exit /b 1
)

:: Execute auto_login.py using full path
"%PY_CMD%" "%~dp0auto_login.py" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================
    echo [ERROR] Execution failed.
    echo ========================================================
    pause
)
