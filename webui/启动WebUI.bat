@echo off
chcp 65001 >/dev/null
title yt-dlp WebUI
set PYTHONPATH=%~dp0..
cd /d "%~dp0backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
