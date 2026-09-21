@echo off
chcp 65001 >/dev/null
title yt-dlp WebUI Dev
set PYTHONPATH=%~dp0..
set YTDL_WEBUI_DEV=1
cd /d "%~dp0backend"
start python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
cd /d "%~dp0frontend"
start npm run dev
echo.
echo Backend:  http://localhost:8000
echo Frontend: http://localhost:5173
echo.
pause
