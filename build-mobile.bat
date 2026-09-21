@echo off
echo ============================================
echo   VideoMover - Mobile APK Build
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] Building mobile frontend...
cd mobile-frontend
call npm run build
if errorlevel 1 (
    echo [ERROR] Frontend build failed
    pause
    exit /b 1
)
cd ..

echo [2/3] Copying frontend to Android project...
python -c "import shutil,os;[shutil.rmtree(d,ignore_errors=True) or shutil.copytree(r'mobile-frontend\dist',d) for d in [r'webui\android-app\app\src\main\assets',r'webui\android-app\app\src\main\python\static']]"

REM Copy bundled ffmpeg binary to assets (after frontend copy which clears the directory)
copy /y "webui\android-app\ffmpeg-binary\ffmpeg" "webui\android-app\app\src\main\assets\ffmpeg" >nul 2>&1
if exist "webui\android-app\app\src\main\assets\ffmpeg" (
    echo   ffmpeg binary copied to assets
) else (
    echo   [WARNING] ffmpeg binary not found, skipping
)

echo [3/3] Building APK...
cd webui\android-app
call java -jar D:/Android/gradle-8.7/lib/gradle-launcher-8.7.jar clean assembleDebug --no-daemon
if errorlevel 1 (
    echo [ERROR] APK build failed
    pause
    exit /b 1
)
cd ..\..

copy /y "webui\android-app\app\build\outputs\apk\debug\app-debug.apk" "VideoMover.apk" >nul

echo.
echo ============================================
echo   Build done! Output: VideoMover.apk
echo ============================================
pause
