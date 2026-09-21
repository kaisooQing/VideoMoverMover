"""Download API endpoints - Android adapted."""
import asyncio
import os
import sys
import uuid
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from ..download_manager import download_manager
from ..models import DownloadRequest, DownloadTaskInfo

router = APIRouter(prefix="/api/downloads", tags=["downloads"])

# Directory for uploaded cookie files
if 'ANDROID_ROOT' in os.environ:
    COOKIE_DIR = os.path.join('/data/data/com.ytdlp.webui/files', 'cookies')
elif getattr(sys, 'frozen', False):
    COOKIE_DIR = os.path.join(os.path.dirname(sys.executable), 'cookies')
else:
    COOKIE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cookies')
try:
    os.makedirs(COOKIE_DIR, exist_ok=True)
except Exception:
    pass


class InfoRequest(BaseModel):
    url: str


@router.post("")
async def create_download(request: DownloadRequest):
    """Create download task(s) for one or more URLs."""
    task_ids = download_manager.start_download(request)
    return {"task_ids": task_ids}


@router.get("")
async def list_downloads(status: str = "all"):
    """List all download tasks, optionally filtered by status."""
    return download_manager.get_all_tasks(status_filter=status)


@router.get("/{task_id}")
async def get_download(task_id: str):
    """Get details of a specific download task."""
    task = download_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.to_info()


@router.delete("/{task_id}")
async def cancel_download(task_id: str):
    """Cancel a running download task."""
    cancelled = download_manager.cancel_download(task_id)
    return {"cancelled": cancelled}


@router.post("/info")
async def extract_info(request: InfoRequest):
    """Extract video info without downloading (for preview)."""
    try:
        info = download_manager.extract_info(request.url)
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cookies/upload")
async def upload_cookies(file: UploadFile = File(...)):
    """Upload a cookies.txt file for authenticated downloads."""
    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="Only .txt cookie files are accepted")

    filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = os.path.join(COOKIE_DIR, filename)

    content = await file.read()
    with open(filepath, 'wb') as f:
        f.write(content)

    return {
        "filename": filename,
        "path": filepath,
        "size": len(content),
        "message": f"Cookie file uploaded successfully ({len(content)} bytes)"
    }


@router.get("/cookies/list")
async def list_cookies():
    """List uploaded cookie files."""
    files = []
    for f in os.listdir(COOKIE_DIR):
        if f.endswith('.txt'):
            filepath = os.path.join(COOKIE_DIR, f)
            files.append({
                "filename": f,
                "path": filepath,
                "size": os.path.getsize(filepath),
            })
    return files


class AutoCookieRequest(BaseModel):
    url: str


@router.post("/cookies/auto")
async def auto_fetch_cookies(request: AutoCookieRequest):
    """Automatically fetch cookies - not available on Android."""
    from ..auto_cookies import fetch_cookies_sync
    result = await asyncio.get_event_loop().run_in_executor(
        None, fetch_cookies_sync, request.url
    )
    if 'error' in result:
        raise HTTPException(status_code=500, detail=result['error'])
    return result
