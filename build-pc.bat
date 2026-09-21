@echo off
echo ============================================
echo   Papake - PC EXE Build
echo ============================================
echo.

cd /d "%~dp0"

echo [1/1] Building PC EXE...
cd webui\backend
call "%~dp0webui\.venv\Scripts\python.exe" -m PyInstaller --clean "%~dp0webui\build\yt-dlp-webui.spec"
if errorlevel 1 (
    echo [ERROR] EXE build failed
    pause
    exit /b 1
)
cd ..\..

copy /y "webui\backend\dist\yt-dlp-webui.exe" "papake.exe" >nul

echo.
echo ============================================
echo   Build done! Output: papake.exe
echo ============================================
pause
