"""Simplified FastAPI app for Android - avoids problematic platform-specific imports."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
import uuid
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List
from urllib.parse import urlencode

from fastapi import FastAPI, WebSocket
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .utils import (
    _get_android_context, _get_download_dir, scan_downloaded_file,
    _extract_url, _detect_platform, _normalize_platform_url,
    _resolve_douyin_url, _fetch_douyin_ttwid,
)
from .platforms import (
    _download_douyin_direct,
    _download_kuaishou_direct,
    _download_xiaohongshu_direct,
    _download_bilibili_direct,
    _run_ytdlp_download,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Skip yt-dlp root path addition on Android
if 'ANDROID_ROOT' not in os.environ:
    _ytdlp_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    if _ytdlp_root not in sys.path:
        sys.path.insert(0, _ytdlp_root)


# Simple models

class DownloadRequest(BaseModel):
    urls: List[str] = Field(..., min_items=1)
    download_dir: Optional[str] = None
    format_option: Optional[dict] = None
    cookie_browser: Optional[str] = None
    cookie_file: Optional[str] = None
    proxy: Optional[str] = None
    output_template: str = "%(title)s.%(ext)s"


class TaskInfo(BaseModel):
    id: str
    url: str
    status: str = "queued"
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    progress_pct: float = 0.0
    speed: Optional[str] = None
    eta: Optional[str] = None
    filename: Optional[str] = None
    filesize: Optional[str] = None
    error: Optional[str] = None
    created_at: float = 0.0
    completed_at: Optional[float] = None


# Task storage
_tasks = {}
_ws_clients = set()

_COOKIE_DIR = "/data/data/com.ytdlp.webui/files/cookies"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("视频搬运工 started on Android")
    asyncio.create_task(_broadcast_progress())
    yield
    logger.info("视频搬运工 stopped")


app = FastAPI(title="视频搬运工", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "platform": "android"}


@app.post("/api/downloads")
async def create_download(request: DownloadRequest):
    """Create download task(s)."""
    # Always use app's private directory on Android to avoid permission issues
    download_dir = _get_download_dir()
    logger.info(f"Using download_dir: {download_dir}")
    
    os.makedirs(download_dir, exist_ok=True)
    
    task_ids = []
    for url in request.urls:
        clean_url = _extract_url(url)
        task_id = str(uuid.uuid4())[:8]
        _tasks[task_id] = {
            "id": task_id,
            "url": clean_url,
            "status": "queued",
            "title": None,
            "thumbnail": None,
            "progress_pct": 0.0,
            "speed": None,
            "eta": None,
            "filename": None,
            "filesize": None,
            "error": None,
            "created_at": time.time(),
            "completed_at": None,
        }
        
        thread = threading.Thread(
            target=_run_ytdlp_download,
            args=(_tasks[task_id], clean_url, download_dir),
            daemon=True
        )
        thread.start()
        task_ids.append(task_id)
        logger.info(f"Created task {task_id} for {clean_url}")
    
    return {"task_ids": task_ids}


@app.get("/api/downloads")
async def list_downloads(status: str = "all"):
    """List all download tasks."""
    tasks = list(_tasks.values())
    if status != "all":
        tasks = [t for t in tasks if t.get('status') == status]
    tasks.sort(key=lambda t: t.get('created_at', 0), reverse=True)
    return tasks


@app.get("/api/downloads/{task_id}")
async def get_download(task_id: str):
    """Get specific task."""
    task = _tasks.get(task_id)
    if not task:
        return {"error": "Task not found"}
    return task


@app.delete("/api/downloads/{task_id}")
async def cancel_download(task_id: str):
    """Cancel download (not fully implemented)."""
    if task_id in _tasks:
        _tasks[task_id]['status'] = 'cancelled'
        _tasks[task_id]['completed_at'] = time.time()
    return {"cancelled": True}


@app.post("/api/downloads/info")
async def extract_info(request: dict):
    """Extract video info."""
    url = request.get('url', '')
    try:
        from yt_dlp import YoutubeDL
        with YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return {
                    'id': info.get('id'),
                    'title': info.get('title'),
                    'thumbnail': info.get('thumbnail'),
                    'duration': info.get('duration'),
                    'uploader': info.get('uploader'),
                }
    except Exception as e:
        return {"error": str(e)}
    return {}


@app.get("/api/settings")
async def get_settings():
    return {
        "download_dir": _get_download_dir(),
        "max_concurrent": 3,
        "proxy": None,
        "output_template": "%(title)s.%(ext)s",
        "theme": "dark",
    }


@app.put("/api/settings")
async def update_settings(request: dict):
    return request


@app.get("/api/system/drives")
async def list_drives():
    drives = []
    if os.path.exists('/storage/emulated/0'):
        drives.append('/storage/emulated/0/')
    return drives


@app.get("/api/system/directories")
async def list_directories(path: str = ""):
    if not path:
        items = []
        if os.path.exists('/storage/emulated/0'):
            items.append({'name': 'Internal Storage', 'is_dir': True, 'path': '/storage/emulated/0'})
        return {'path': '', 'children': items}
    
    if not os.path.isdir(path):
        return {'path': path, 'children': [], 'error': 'Not a directory'}
    
    children = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isdir(full) and not name.startswith('.'):
                children.append({'name': name, 'is_dir': True, 'path': full})
    except Exception:
        pass
    return {'path': path, 'children': children}


@app.get("/api/system/browsers")
async def list_browsers():
    return []


@app.get("/api/system/ffmpeg")
async def check_ffmpeg():
    return {'available': False, 'path': None}


@app.get("/api/system/proxy-image")
async def proxy_image(url: str = '', path: str = ''):
    """Proxy external images or read local image files."""
    # Local file path mode
    if path:
        if not os.path.exists(path):
            return Response(status_code=404)
        try:
            with open(path, 'rb') as f:
                data = f.read()
            ext = os.path.splitext(path)[1].lower()
            ct_map = {'.webp': 'image/webp', '.png': 'image/png', '.gif': 'image/gif'}
            return Response(content=data, media_type=ct_map.get(ext, 'image/jpeg'))
        except Exception:
            return Response(status_code=500)

    if not url:
        return Response(status_code=400)

    url_lower = url.lower().split('?')[0]
    if url_lower.endswith('.webp'):
        content_type = 'image/webp'
    elif url_lower.endswith('.png'):
        content_type = 'image/png'
    elif url_lower.endswith('.gif'):
        content_type = 'image/gif'
    else:
        content_type = 'image/jpeg'

    # Platform-specific Referer
    url_host = ''
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        url_host = parsed.hostname or ''
    except Exception:
        pass

    if 'hdslb.com' in url_host or 'bili' in url_host:
        referer = 'https://www.bilibili.com/'
    elif 'xhscdn.com' in url_host or 'xiaohongshu' in url_host:
        referer = 'https://www.xiaohongshu.com/'
    elif 'kuaishou.com' in url_host or 'ks-sns.com' in url_host or 'kpf.kz' in url_host or 'gifshow.com' in url_host:
        referer = 'https://www.kuaishou.com/'
    elif 'douyinvod.com' in url_host or 'douyin' in url_host or 'bytedance' in url_host or 'pstatp.com' in url_host:
        referer = 'https://www.douyin.com/'
    else:
        referer = url

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'
        ),
        'Referer': referer,
    }

    try:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read()
        resp.close()
        ct = resp.headers.get('Content-Type', '')
        if ct and ct.startswith('image/'):
            content_type = ct.split(';')[0].strip()
        return Response(content=data, media_type=content_type)
    except Exception:
        return Response(status_code=502)


@app.get("/api/system/error-log")
async def get_error_log():
    """Return the error log content for debugging."""
    log_path = "/data/data/com.ytdlp.webui/files/server_error.log"
    try:
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"content": content, "path": log_path}
        else:
            return {"content": "No error log found", "path": log_path}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/system/test-ytdlp")
async def test_ytdlp():
    """Test if yt-dlp is importable and working."""
    result = {"import": False, "error": None}
    try:
        import yt_dlp
        result["import"] = True
        result["version"] = getattr(yt_dlp, 'version', 'unknown')
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
                result["ydl_init"] = True
        except Exception as e:
            result["ydl_init"] = False
            result["ydl_error"] = str(e)
    except Exception as e:
        result["error"] = str(e)
    return result


# --- File operations (open-file, open-folder, file-type) ---

_VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.ts', '.rmvb', '.rm'}
_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.heic', '.avif'}
_AUDIO_EXTS = {'.mp3', '.aac', '.flac', '.wav', '.ogg', '.m4a', '.wma', '.opus'}


class FileActionRequest(BaseModel):
    path: str


@app.post("/api/system/open-file")
async def open_file(req: FileActionRequest):
    """Open a file using Android Intent with FileProvider."""
    path = req.path
    if not path or not os.path.exists(path):
        return {'success': False, 'error': '文件不存在'}
    try:
        from java import jclass
        context = _get_android_context()
        if context is None:
            return {'success': False, 'error': '无法获取 Android Context'}
        package_name = context.getPackageName()

        # Determine MIME type
        ext = os.path.splitext(path)[1].lower()
        mime_map = {
            '.mp4': 'video/mp4', '.mkv': 'video/x-matroska', '.avi': 'video/x-msvideo',
            '.mov': 'video/quicktime', '.webm': 'video/webm', '.flv': 'video/x-flv',
            '.wmv': 'video/x-ms-wmv', '.m4v': 'video/mp4', '.ts': 'video/mp2t',
            '.rmvb': 'video/vnd.rn-realvideo', '.rm': 'video/vnd.rn-realvideo',
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
            '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
            '.mp3': 'audio/mpeg', '.aac': 'audio/aac', '.flac': 'audio/flac',
            '.wav': 'audio/wav', '.ogg': 'audio/ogg', '.m4a': 'audio/mp4',
        }
        mime_type = mime_map.get(ext, 'application/octet-stream')

        # Get content URI via FileProvider
        file_obj = jclass("java.io.File")(path)
        uri = jclass("androidx.core.content.FileProvider").getUriForFile(
            context, package_name + ".fileprovider", file_obj
        )

        # Create Intent
        intent = jclass("android.content.Intent")("android.intent.action.VIEW")
        intent.setDataAndType(uri, mime_type)
        intent.addFlags(1)  # FLAG_GRANT_READ_URI_PERMISSION
        intent.addFlags(0x10000000)  # FLAG_ACTIVITY_NEW_TASK
        context.startActivity(intent)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.post("/api/system/open-folder")
async def open_folder(req: FileActionRequest):
    """Open the containing folder using Android Intent with FileProvider."""
    path = req.path
    if not path:
        return {'success': False, 'error': '未提供路径'}
    folder = os.path.dirname(path) if os.path.isfile(path) else path
    if not os.path.exists(folder):
        return {'success': False, 'error': '文件夹不存在'}
    try:
        from java import jclass
        context = _get_android_context()
        if context is None:
            return {'success': False, 'error': '无法获取 Android Context'}
        package_name = context.getPackageName()

        # Use FileProvider to get content:// URI (file:// is blocked on Android 7.0+)
        folder_obj = jclass("java.io.File")(folder)
        uri = jclass("androidx.core.content.FileProvider").getUriForFile(
            context, package_name + ".fileprovider", folder_obj
        )

        # Open folder with a file manager
        intent = jclass("android.content.Intent")("android.intent.action.VIEW")
        intent.setDataAndType(uri, "vnd.android.document/directory")
        intent.addFlags(1)  # FLAG_GRANT_READ_URI_PERMISSION
        intent.addFlags(0x10000000)  # FLAG_ACTIVITY_NEW_TASK
        context.startActivity(intent)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@app.post("/api/system/file-type")
async def get_file_type(req: FileActionRequest):
    """Detect file type for UI icon display."""
    path = req.path
    if not path:
        return {'type': 'unknown'}
    if os.path.isdir(path):
        return {'type': 'folder'}
    ext = os.path.splitext(path)[1].lower()
    if ext in _VIDEO_EXTS:
        return {'type': 'video'}
    if ext in _IMAGE_EXTS:
        return {'type': 'image'}
    if ext in _AUDIO_EXTS:
        return {'type': 'audio'}
    return {'type': 'unknown'}


@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """WebSocket for real-time progress updates."""
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Handle subscribe/unsubscribe if needed
    except Exception:
        pass
    finally:
        _ws_clients.discard(websocket)


_scanned_tasks = set()  # track tasks already scanned by MediaScanner

async def _broadcast_progress():
    """Periodically broadcast task updates to WebSocket clients."""
    last_states = {}  # track last sent state per task to avoid redundant updates
    while True:
        if _ws_clients:
            for task_id, task in list(_tasks.items()):
                # Trigger MediaScanner when download completes so gallery sees it immediately
                if task.get("status") == "completed" and task_id not in _scanned_tasks:
                    filepath = task.get("filename")
                    if filepath and os.path.exists(filepath):
                        scan_downloaded_file(filepath)
                    _scanned_tasks.add(task_id)

                # Build the update message in the format frontend expects
                update = {
                    "task_id": task_id,
                    "url": task.get("url", ""),
                    "status": task.get("status", "queued"),
                    "title": task.get("title") or "",
                    "thumbnail": task.get("thumbnail"),
                    "progress_pct": task.get("progress_pct", 0.0),
                    "speed": task.get("speed"),
                    "eta": task.get("eta"),
                    "filename": task.get("filename"),
                    "filesize": task.get("filesize"),
                    "error": task.get("error"),
                    "completed_at": task.get("completed_at"),
                    "created_at": task.get("created_at"),
                }
                # Only send if state changed
                state_key = (update["status"], update["progress_pct"], update["filename"], update.get("completed_at"))
                if task_id not in last_states or last_states[task_id] != state_key:
                    last_states[task_id] = state_key
                    for ws in list(_ws_clients):
                        try:
                            await ws.send_json(update)
                        except Exception:
                            _ws_clients.discard(ws)
        await asyncio.sleep(0.5)


# Serve static files
def _get_static_dir() -> Optional[Path]:
    if 'ANDROID_ROOT' in os.environ:
        this_dir = os.path.dirname(os.path.abspath(__file__))
        parent = os.path.dirname(this_dir)
        static = os.path.join(parent, 'static')
        if os.path.isdir(static):
            return Path(static)
    return None


static_dir = _get_static_dir()
if static_dir:
    assets_dir = static_dir / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        index = static_dir / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return {"detail": "Not found"}, 404
