@echo off
setlocal
cd /d "%~dp0"
set "PATH=C:\Program Files\Git\cmd;%PATH%"

title Push naver-auto to GitHub

echo ========================================================
echo   Pushing naver-auto to GitHub (main branch)
echo   Repository: https://github.com/jelwang0989-dot/naver-auto
echo ========================================================
echo.

git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================
    echo   [SUCCESS] GitHub push completed!
    echo ========================================================
) else (
    echo.
    echo [INFO] If prompted for GitHub login, please sign in.
)
pause
