"""System info API endpoints."""
from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel
import os
import shutil
import subprocess
import sys
import urllib.request

router = APIRouter(prefix="/api/system", tags=["system"])

SUPPORTED_BROWSERS = [
    'chrome', 'firefox', 'edge', 'brave', 'opera', 'vivaldi',
    'chromium', 'safari',
]

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.ts', '.rmvb', '.rm'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.heic', '.avif'}
AUDIO_EXTS = {'.mp3', '.aac', '.flac', '.wav', '.ogg', '.m4a', '.wma', '.opus'}


def _detect_file_type(path: str) -> str:
    """Detect file type from extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXTS:
        return 'video'
    if ext in IMAGE_EXTS:
        return 'image'
    if ext in AUDIO_EXTS:
        return 'audio'
    return 'unknown'


class FileActionRequest(BaseModel):
    path: str


@router.post("/open-file")
async def open_file(req: FileActionRequest):
    """Open a file with the system default application (play video, view image, etc.)."""
    path = req.path
    if not path or not os.path.exists(path):
        return {'success': False, 'error': 'File not found'}

    try:
        if sys.platform == 'win32':
            # Use explorer to handle paths with special chars like #
            subprocess.Popen(['explorer', path])
        else:
            subprocess.Popen(['xdg-open', path])
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@router.post("/open-folder")
async def open_folder(req: FileActionRequest):
    """Open the containing folder in system file explorer, selecting the file."""
    path = req.path
    if not path:
        return {'success': False, 'error': 'No path provided'}

    try:
        if os.path.isfile(path):
            folder = os.path.dirname(path)
            if sys.platform == 'win32':
                # Use list args to avoid shell escaping issues with # etc.
                subprocess.Popen(['explorer', '/select,', path])
            else:
                subprocess.Popen(['xdg-open', folder])
        elif os.path.isdir(path):
            if sys.platform == 'win32':
                subprocess.Popen(['explorer', path])
            else:
                subprocess.Popen(['xdg-open', path])
        else:
            return {'success': False, 'error': 'Path not found'}
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}


@router.post("/file-type")
async def get_file_type(req: FileActionRequest):
    """Detect file type (video/image/audio/unknown) from path."""
    path = req.path
    if not path:
        return {'type': 'unknown'}
    if os.path.isdir(path):
        return {'type': 'folder'}
    return {'type': _detect_file_type(path)}


@router.get("/browsers")
async def list_browsers():
    """List browsers available for cookie extraction."""
    return SUPPORTED_BROWSERS


@router.get("/drives")
async def list_drives():
    """List available drive letters (Windows)."""
    drives = []
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        drive = f'{letter}:\\'
        if os.path.exists(drive):
            drives.append(drive)
    return drives


@router.get("/directories")
async def list_directories(path: str = ""):
    """Browse directory tree for the directory picker."""
    if not path:
        # Return drives
        items = []
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            drive = f'{letter}:\\'
            if os.path.exists(drive):
                items.append({'name': drive, 'is_dir': True, 'path': drive})
        return {'path': '', 'children': items}

    if not os.path.isdir(path):
        return {'path': path, 'children': [], 'error': 'Not a directory'}

    children = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isdir(full) and not name.startswith('.'):
                children.append({
                    'name': name,
                    'is_dir': True,
                    'path': full,
                })
    except PermissionError:
        return {'path': path, 'children': children, 'error': 'Permission denied'}

    return {'path': path, 'children': children}


@router.get("/ffmpeg")
async def check_ffmpeg():
    """Check if ffmpeg is available on the system."""
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return {'available': True, 'path': ffmpeg_path}
    return {'available': False, 'path': None}


@router.get("/proxy-image")
async def proxy_image(url: str = '', path: str = ''):
    """Proxy external images or read local image files.

    - `url`: External image URL to proxy (avoids CORS/referer restrictions)
    - `path`: Local file path to read directly
    """
    # Local file path mode
    if path:
        if not os.path.exists(path):
            return Response(status_code=404)
        try:
            with open(path, 'rb') as f:
                data = f.read()
            ext = os.path.splitext(path)[1].lower()
            ct_map = {'.webp': 'image/webp', '.png': 'image/png', '.gif': 'image/gif'}
            content_type = ct_map.get(ext, 'image/jpeg')
            return Response(content=data, media_type=content_type)
        except Exception:
            return Response(status_code=500)

    if not url:
        return Response(status_code=400)

    # Determine content type from URL
    url_lower = url.lower().split('?')[0]
    if url_lower.endswith('.webp'):
        content_type = 'image/webp'
    elif url_lower.endswith('.png'):
        content_type = 'image/png'
    elif url_lower.endswith('.gif'):
        content_type = 'image/gif'
    else:
        content_type = 'image/jpeg'

    # Set platform-specific Referer to pass CDN anti-hotlinking
    referer = url
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
    elif 'kuaishou.com' in url_host or 'ks-sns.com' in url_host or 'kpf.kz' in url_host or 'gifshow.com' in url_host or 'kuaishou' in url_host:
        referer = 'https://www.kuaishou.com/'
    elif 'douyinvod.com' in url_host or 'douyin' in url_host or 'bytedance' in url_host or 'pstatp.com' in url_host:
        referer = 'https://www.douyin.com/'
    else:
        referer = url

    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0'
        ),
        'Referer': referer,
    }

    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read()
        resp.close()

        # Detect actual content type from response headers
        ct = resp.headers.get('Content-Type', '')
        if ct and ct.startswith('image/'):
            content_type = ct.split(';')[0].strip()

        return Response(content=data, media_type=content_type)
    except Exception:
        return Response(status_code=502)
