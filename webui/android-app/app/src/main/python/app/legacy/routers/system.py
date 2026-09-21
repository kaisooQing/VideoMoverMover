"""System info API endpoints - Android adapted."""
from fastapi import APIRouter
from pydantic import BaseModel
import os
import shutil
import sys

router = APIRouter(prefix="/api/system", tags=["system"])

VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.ts', '.rmvb', '.rm'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg', '.heic', '.avif'}
AUDIO_EXTS = {'.mp3', '.aac', '.flac', '.wav', '.ogg', '.m4a', '.wma', '.opus'}


def _is_android():
    return 'ANDROID_ROOT' in os.environ or hasattr(sys, 'android_api_level')


def _detect_file_type(path: str) -> str:
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
    """Open a file - on Android, return success (handled by WebView)."""
    path = req.path
    if not path or not os.path.exists(path):
        return {'success': False, 'error': 'File not found'}
    # On Android, file opening is handled by the WebView/Android intent system
    return {'success': True, 'message': 'File available at: ' + path}


@router.post("/open-folder")
async def open_folder(req: FileActionRequest):
    """Open folder - on Android, return success."""
    path = req.path
    if not path:
        return {'success': False, 'error': 'No path provided'}
    return {'success': True, 'message': 'Folder available at: ' + path}


@router.post("/file-type")
async def get_file_type(req: FileActionRequest):
    path = req.path
    if not path:
        return {'type': 'unknown'}
    if os.path.isdir(path):
        return {'type': 'folder'}
    return {'type': _detect_file_type(path)}


@router.get("/browsers")
async def list_browsers():
    """No browsers available for cookie extraction on Android."""
    return []


@router.get("/drives")
async def list_drives():
    """List storage directories on Android."""
    if _is_android():
        # Return common Android storage paths
        drives = []
        # Internal storage
        internal = '/storage/emulated/0'
        if os.path.exists(internal):
            drives.append(internal + '/')
        # App private files dir
        files_dir = '/data/data/com.ytdlp.webui/files'
        if os.path.exists(files_dir):
            drives.append(files_dir + '/')
        # SD card
        sdcard = '/storage/sdcard1'
        if os.path.exists(sdcard):
            drives.append(sdcard + '/')
        return drives
    # Windows fallback
    drives = []
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        drive = f'{letter}:\\'
        if os.path.exists(drive):
            drives.append(drive)
    return drives


@router.get("/directories")
async def list_directories(path: str = ""):
    """Browse directory tree."""
    if _is_android():
        return _list_directories_android(path)
    return _list_directories_default(path)


def _list_directories_android(path: str):
    """Android-specific directory listing."""
    if not path:
        # Return root storage locations
        items = []
        # Internal storage
        internal = '/storage/emulated/0'
        if os.path.exists(internal):
            items.append({'name': 'Internal Storage', 'is_dir': True, 'path': internal})
        # Downloads
        downloads = '/storage/emulated/0/Download'
        if os.path.exists(downloads):
            items.append({'name': 'Downloads', 'is_dir': True, 'path': downloads})
        # App files
        app_files = '/data/data/com.ytdlp.webui/files'
        os.makedirs(app_files, exist_ok=True)
        items.append({'name': 'App Data', 'is_dir': True, 'path': app_files})
        return {'path': '', 'children': items}
    return _list_dir_contents(path)


def _list_directories_default(path: str):
    """Default (Windows) directory listing."""
    if not path:
        items = []
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            drive = f'{letter}:\\'
            if os.path.exists(drive):
                items.append({'name': drive, 'is_dir': True, 'path': drive})
        return {'path': '', 'children': items}
    return _list_dir_contents(path)


def _list_dir_contents(path: str):
    """List directory contents."""
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
    """Check if ffmpeg is available."""
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return {'available': True, 'path': ffmpeg_path}
    # On Android, check common ffmpeg locations
    for p in ['/data/data/com.ytdlp.webui/files/ffmpeg',
              '/data/local/tmp/ffmpeg']:
        if os.path.exists(p):
            return {'available': True, 'path': p}
    return {'available': False, 'path': None}
