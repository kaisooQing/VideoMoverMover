"""Download orchestrator: bridges FastAPI async with yt-dlp's sync API."""
from __future__ import annotations
import asyncio
import logging
import re
import sys
import os
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional

from .models import (
    DownloadRequest, DownloadStatus, DownloadTaskInfo, FormatOption
)
from .config import get_settings

logger = logging.getLogger(__name__)

# Ensure yt_dlp is importable (skip in frozen mode - yt-dlp is bundled)
if not getattr(sys, 'frozen', False):
    _ytdlp_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    if _ytdlp_root not in sys.path:
        sys.path.insert(0, _ytdlp_root)


@dataclass
class DownloadTask:
    """Internal download task state."""
    id: str
    url: str
    status: DownloadStatus = DownloadStatus.QUEUED
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    progress_pct: float = 0.0
    speed: Optional[str] = None
    eta: Optional[str] = None
    filename: Optional[str] = None
    filesize: Optional[str] = None
    error: Optional[str] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    info_dict: Optional[dict] = None

    def to_info(self) -> DownloadTaskInfo:
        return DownloadTaskInfo(
            id=self.id,
            url=self.url,
            status=self.status,
            title=self.title,
            thumbnail=self.thumbnail,
            progress_pct=self.progress_pct,
            speed=self.speed,
            eta=self.eta,
            filename=self.filename,
            filesize=self.filesize,
            error=self.error,
            created_at=self.created_at,
            completed_at=self.completed_at,
        )


def _format_size(size_bytes):
    if not size_bytes:
        return None
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size_bytes < 1024:
            return f'{size_bytes:.1f} {unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f} TB'


def _format_eta(seconds):
    if seconds is None:
        return None
    if seconds < 60:
        return f'{int(seconds)}s'
    if seconds < 3600:
        return f'{int(seconds // 60)}m {int(seconds % 60)}s'
    return f'{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m'


def _format_speed(speed_bytes):
    if not speed_bytes:
        return None
    return _format_size(speed_bytes) + '/s'


def _build_ydl_opts(request: DownloadRequest, task: DownloadTask, progress_hook) -> dict:
    """Convert a DownloadRequest into yt-dlp options dict."""
    settings = get_settings()

    # Resolve download directory
    out_dir = request.download_dir or settings.download_dir
    os.makedirs(out_dir, exist_ok=True)

    opts = {
        'outtmpl': os.path.join(out_dir, request.output_template),
        'progress_hooks': [progress_hook],
        'noplaylist': False,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'socket_timeout': 60,
        'retries': 3,
        'fragment_retries': 3,
        'http_chunk_size': 10485760,  # 10MB chunks for more reliable progress
    }

    # Format selection
    fmt = request.format_option
    if fmt.mode == 'best':
        opts['format'] = 'bestvideo+bestaudio/best'
    elif fmt.mode == 'worst':
        opts['format'] = 'worstvideo+worstaudio/worst'
    elif fmt.mode == 'audio_only':
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif fmt.mode == 'custom' and fmt.format_string:
        opts['format'] = fmt.format_string

    # Cookies
    if request.cookie_browser:
        opts['cookiesfrombrowser'] = (request.cookie_browser,)
    elif request.cookie_file:
        opts['cookiefile'] = request.cookie_file

    # Proxy
    proxy = request.proxy or settings.proxy
    if proxy:
        opts['proxy'] = proxy

    # Subtitles
    sub = request.subtitle_options
    if sub.enabled:
        opts['writesubtitles'] = True
        opts['writeautomaticsub'] = sub.auto_subs
        opts['subtitleslangs'] = [s.strip() for s in sub.languages.split(',')]
        opts['subtitlesformat'] = sub.sub_format
        if sub.embed_subs:
            opts.setdefault('postprocessors', []).append({
                'key': 'FFmpegEmbedSubtitle',
            })

    # Embed metadata / thumbnail
    if request.embed_metadata:
        opts.setdefault('postprocessors', []).append({
            'key': 'FFmpegMetadata',
            'add_metadata': True,
        })
    if request.embed_thumbnail:
        opts.setdefault('postprocessors', []).append({
            'key': 'EmbedThumbnail',
        })
    if request.write_thumbnail:
        opts['writethumbnail'] = True

    # ffmpeg location
    if settings.ffmpeg_path:
        opts['ffmpeg_location'] = settings.ffmpeg_path

    # Bilibili: add Referer to avoid 412 Precondition Failed
    if 'bilibili' in task.url or 'b23.tv' in task.url:
        opts.setdefault('http_headers', {})
        opts['http_headers']['Referer'] = 'https://www.bilibili.com'
        opts['http_headers']['User-Agent'] = (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0'
        )

    return opts


# Regex to extract URLs from share text (handles Douyin, TikTok, Bilibili, etc.)
_URL_RE = re.compile(r'https?://[^\s<>"\u200b\u200c\u200d\u2060\ufeff]+')


def extract_url(text: str) -> str:
    """Extract the first video URL from share text.

    Apps like Douyin/TikTok copy a block of text with the URL embedded.
    This function finds and returns the actual URL.
    """
    text = text.strip()
    # If the text is already a clean URL, return as-is
    if re.fullmatch(r'https?://\S+', text):
        return text
    # Extract the first http(s) URL found in the text
    match = _URL_RE.search(text)
    if match:
        url = match.group(0).rstrip('/')
        # Remove trailing punctuation that's unlikely part of the URL
        url = url.rstrip('.,;:!?）)】」』》')
        return url
    return text  # Fallback: return original (will fail at yt-dlp level)


class DownloadManager:
    """Manages download tasks using yt-dlp in a thread pool."""

    def __init__(self, max_workers: int = 3, broadcast_callback=None):
        self._tasks: dict[str, DownloadTask] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='ytdlp')
        self._broadcast = broadcast_callback
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def set_broadcast(self, callback):
        self._broadcast = callback

    @property
    def tasks(self) -> dict[str, DownloadTask]:
        return self._tasks

    def get_task(self, task_id: str) -> Optional[DownloadTask]:
        return self._tasks.get(task_id)

    def get_all_tasks(self, status_filter: str = 'all') -> list[DownloadTaskInfo]:
        tasks = list(self._tasks.values())
        if status_filter != 'all':
            tasks = [t for t in tasks if t.status.value == status_filter]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return [t.to_info() for t in tasks]

    def start_download(self, request: DownloadRequest) -> list[str]:
        """Create and start download tasks for each URL. Returns task IDs."""
        task_ids = []
        for raw_url in request.urls:
            url = extract_url(raw_url)
            task_id = str(uuid.uuid4())[:8]
            task = DownloadTask(id=task_id, url=url)
            self._tasks[task_id] = task
            task_ids.append(task_id)
            self._executor.submit(self._run_download, task, request)
        return task_ids

    def cancel_download(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task and task.status in (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING):
            task.cancel_event.set()
            task.status = DownloadStatus.CANCELLED
            task.completed_at = time.time()
            self._emit_progress(task)
            return True
        return False

    def _emit_progress(self, task: DownloadTask):
        """Send progress update via broadcast callback."""
        if not self._broadcast or not self._loop:
            return
        data = {
            'task_id': task.id,
            'status': task.status.value,
            'title': task.title,
            'thumbnail': task.thumbnail,
            'progress_pct': task.progress_pct,
            'speed': task.speed,
            'eta': task.eta,
            'filename': task.filename,
            'filesize': task.filesize,
            'error': task.error,
            'created_at': task.created_at,
            'completed_at': task.completed_at,
        }
        asyncio.run_coroutine_threadsafe(self._broadcast(task.id, data), self._loop)

    def _run_download(self, task: DownloadTask, request: DownloadRequest):
        """Run download in a worker thread. Routes to platform-specific handlers."""
        from .douyin_f2 import is_douyin_url, is_f2_available
        from .kuaishou_download import is_kuaishou_url
        from .bilibili_download import is_bilibili_url
        from .xiaohongshu_download import is_xiaohongshu_url
        from .wechat_channels_download import is_wechat_channels_url

        url = task.url

        # Douyin: use f2 library if available (yt-dlp's Douyin extractor may fail without a_bogus)
        if is_douyin_url(url) and is_f2_available():
            self._run_douyin_download(task, request)
            return

        # Kuaishou: use custom mobile UA approach (yt-dlp has no Kuaishou extractor)
        if is_kuaishou_url(url):
            self._run_kuaishou_download(task, request)
            return

        # Bilibili: try yt-dlp first (fast), fallback to Playwright on 412
        if is_bilibili_url(url):
            self._run_bilibili_with_fallback(task, request)
            return

        # Xiaohongshu: use custom extraction (yt-dlp only handles videos, not image posts)
        if is_xiaohongshu_url(url):
            self._run_xiaohongshu_download(task, request)
            return

        # WeChat Channels (视频号): use online parser API
        if is_wechat_channels_url(url):
            self._run_wechat_channels_download(task, request)
            return

        # All other platforms: use yt-dlp
        self._run_ytdlp_download(task, request)

    def _run_bilibili_download(self, task: DownloadTask, request: DownloadRequest):
        """Download Bilibili video using Playwright + FFmpeg merge."""
        from .bilibili_download import download_bilibili_sync

        settings = get_settings()
        out_dir = request.download_dir or settings.download_dir

        def progress_callback(title, pct, speed, eta, filesize):
            if task.cancel_event.is_set():
                return
            task.status = DownloadStatus.DOWNLOADING
            if title:
                task.title = title
            task.progress_pct = pct
            task.speed = speed
            task.eta = eta
            task.filesize = filesize
            self._emit_progress(task)

        try:
            task.status = DownloadStatus.DOWNLOADING
            self._emit_progress(task)

            result = download_bilibili_sync(
                url=task.url,
                download_dir=out_dir,
                progress_callback=progress_callback,
                cancel_event=task.cancel_event,
            )

            if 'error' in result:
                err = result['error']
                if 'cancelled' in err.lower():
                    task.status = DownloadStatus.CANCELLED
                else:
                    task.status = DownloadStatus.FAILED
                    task.error = err
                task.completed_at = time.time()
                self._emit_progress(task)
                return

            # Success
            task.status = DownloadStatus.COMPLETED
            task.progress_pct = 100.0
            task.title = result.get('title', task.title)
            task.thumbnail = result.get('thumbnail')
            task.filename = result.get('filepath', '')
            task.filesize = _format_size(result.get('filesize', 0))
            task.completed_at = time.time()
            self._emit_progress(task)

        except Exception as e:
            err_msg = str(e)
            if 'cancelled' in err_msg.lower():
                task.status = DownloadStatus.CANCELLED
            else:
                task.status = DownloadStatus.FAILED
                task.error = err_msg
            task.completed_at = time.time()
            self._emit_progress(task)

    def _run_bilibili_with_fallback(self, task: DownloadTask, request: DownloadRequest):
        """Try yt-dlp first for Bilibili (fast), fallback to Playwright on 412."""
        try:
            # Attempt 1: yt-dlp (no browser, usually < 1s to start)
            self._run_ytdlp_download(task, request)
            if task.status == DownloadStatus.COMPLETED:
                return
            # If yt-dlp failed with 412, task.status will be FAILED
            err = (task.error or '').lower()
            if '412' not in err and 'precondition' not in err and 'forbidden' not in err and 'blocked' not in err:
                # Non-412 error, no point trying Playwright
                return
            # 412 or similar anti-bot error → fallback to Playwright
            logger.info(f"yt-dlp got 412 for {task.url}, falling back to Playwright")
        except Exception as e:
            logger.info(f"yt-dlp failed for Bilibili: {e}, falling back to Playwright")

        # Reset task state for Playwright retry
        task.status = DownloadStatus.DOWNLOADING
        task.error = None
        task.progress_pct = 0.0
        self._emit_progress(task)

        # Attempt 2: Playwright (slower but more robust)
        self._run_bilibili_download(task, request)

    def _run_kuaishou_download(self, task: DownloadTask, request: DownloadRequest):
        """Download Kuaishou video using mobile UA extraction."""
        from .kuaishou_download import download_kuaishou_sync

        settings = get_settings()
        out_dir = request.download_dir or settings.download_dir

        def progress_callback(title, pct, speed, eta, filesize):
            if task.cancel_event.is_set():
                return
            task.status = DownloadStatus.DOWNLOADING
            if title:
                task.title = title
            task.progress_pct = pct
            task.speed = speed
            task.eta = eta
            task.filesize = filesize
            self._emit_progress(task)

        try:
            task.status = DownloadStatus.DOWNLOADING
            self._emit_progress(task)

            result = download_kuaishou_sync(
                url=task.url,
                download_dir=out_dir,
                progress_callback=progress_callback,
                cancel_event=task.cancel_event,
            )

            if 'error' in result:
                err = result['error']
                if 'cancelled' in err.lower():
                    task.status = DownloadStatus.CANCELLED
                else:
                    task.status = DownloadStatus.FAILED
                    task.error = err
                task.completed_at = time.time()
                self._emit_progress(task)
                return

            # Success
            task.status = DownloadStatus.COMPLETED
            task.progress_pct = 100.0
            task.title = result.get('title', task.title)
            task.thumbnail = result.get('thumbnail')
            task.filename = result.get('filepath', '')
            task.filesize = _format_size(result.get('filesize', 0))
            task.completed_at = time.time()
            self._emit_progress(task)

        except Exception as e:
            err_msg = str(e)
            if 'cancelled' in err_msg.lower():
                task.status = DownloadStatus.CANCELLED
            else:
                task.status = DownloadStatus.FAILED
                task.error = err_msg
            task.completed_at = time.time()
            self._emit_progress(task)

    def _run_xiaohongshu_download(self, task: DownloadTask, request: DownloadRequest):
        """Download Xiaohongshu post (images or video)."""
        from .xiaohongshu_download import download_xiaohongshu_sync

        settings = get_settings()
        out_dir = request.download_dir or settings.download_dir

        def progress_callback(title, pct, speed, eta, filesize):
            if task.cancel_event.is_set():
                return
            task.status = DownloadStatus.DOWNLOADING
            if title:
                task.title = title
            task.progress_pct = pct
            task.speed = speed
            task.eta = eta
            task.filesize = filesize
            self._emit_progress(task)

        try:
            task.status = DownloadStatus.DOWNLOADING
            self._emit_progress(task)

            result = download_xiaohongshu_sync(
                url=task.url,
                download_dir=out_dir,
                progress_callback=progress_callback,
                cancel_event=task.cancel_event,
            )

            if 'error' in result:
                err = result['error']
                if 'cancelled' in err.lower():
                    task.status = DownloadStatus.CANCELLED
                else:
                    task.status = DownloadStatus.FAILED
                    task.error = err
                task.completed_at = time.time()
                self._emit_progress(task)
                return

            # Success
            task.status = DownloadStatus.COMPLETED
            task.progress_pct = 100.0
            task.title = result.get('title', task.title)
            task.thumbnail = result.get('thumbnail')
            task.filename = result.get('filepath', '')
            task.filesize = _format_size(result.get('filesize', 0))
            task.completed_at = time.time()
            self._emit_progress(task)

        except Exception as e:
            err_msg = str(e)
            if 'cancelled' in err_msg.lower():
                task.status = DownloadStatus.CANCELLED
            else:
                task.status = DownloadStatus.FAILED
                task.error = err_msg
            task.completed_at = time.time()
            self._emit_progress(task)

    def _run_douyin_download(self, task: DownloadTask, request: DownloadRequest):
        """Download Douyin video using f2 library."""
        from .douyin_f2 import download_douyin_sync

        settings = get_settings()
        out_dir = request.download_dir or settings.download_dir

        # Resolve cookie file
        cookie_file = request.cookie_file
        if not cookie_file:
            # Use auto-fetched cookies from the cookies directory
            from .douyin_f2 import COOKIE_DIR
            import glob as _glob
            files = _glob.glob(os.path.join(COOKIE_DIR, 'douyin_auto_*.txt'))
            if files:
                cookie_file = sorted(files)[-1]  # latest

        def progress_callback(title, pct, speed, eta, filesize):
            if task.cancel_event.is_set():
                return
            task.status = DownloadStatus.DOWNLOADING
            if title:
                task.title = title
            task.progress_pct = pct
            task.speed = speed
            task.eta = eta
            task.filesize = filesize
            self._emit_progress(task)

        try:
            task.status = DownloadStatus.DOWNLOADING
            self._emit_progress(task)

            result = download_douyin_sync(
                url=task.url,
                download_dir=out_dir,
                cookie_file=cookie_file,
                progress_callback=progress_callback,
                cancel_event=task.cancel_event,
            )

            if 'error' in result:
                err = result['error']
                if 'cancelled' in err.lower():
                    task.status = DownloadStatus.CANCELLED
                else:
                    # Try auto-fetching cookies if cookie error
                    if 'cookie' in err.lower() and not cookie_file:
                        task.error = '需要 Cookie，正在自动获取...'
                        self._emit_progress(task)
                        try:
                            from .auto_cookies import fetch_cookies_sync
                            cookie_result = fetch_cookies_sync(task.url)
                            if 'path' in cookie_result:
                                cookie_file = cookie_result['path']
                                logger.info(f'Auto-fetched cookies: {cookie_file}')
                                task.error = None
                                self._emit_progress(task)
                                result = download_douyin_sync(
                                    url=task.url,
                                    download_dir=out_dir,
                                    cookie_file=cookie_file,
                                    progress_callback=progress_callback,
                                    cancel_event=task.cancel_event,
                                )
                        except Exception as ce:
                            logger.warning(f'Auto-cookie error: {ce}')

                    if 'error' in result:
                        err = result['error']
                        if 'cancelled' in err.lower():
                            task.status = DownloadStatus.CANCELLED
                        else:
                            task.status = DownloadStatus.FAILED
                            task.error = err
                        task.completed_at = time.time()
                        self._emit_progress(task)
                        return

            # Success
            task.status = DownloadStatus.COMPLETED
            task.progress_pct = 100.0
            task.title = result.get('title', task.title)
            task.thumbnail = result.get('thumbnail')
            task.filename = result.get('filepath', '')
            task.filesize = _format_size(result.get('filesize', 0))
            task.completed_at = time.time()
            self._emit_progress(task)

        except Exception as e:
            err_msg = str(e)
            if 'cancelled' in err_msg.lower():
                task.status = DownloadStatus.CANCELLED
            else:
                task.status = DownloadStatus.FAILED
                task.error = err_msg
            task.completed_at = time.time()
            self._emit_progress(task)

    def _run_wechat_channels_download(self, task: DownloadTask, request: DownloadRequest):
        """Download WeChat Channels (视频号) video using online parser API."""
        from .wechat_channels_download import download_wechat_channels_sync

        settings = get_settings()
        out_dir = request.download_dir or settings.download_dir

        def progress_callback(title, pct, speed, eta, filesize):
            if task.cancel_event.is_set():
                return
            task.status = DownloadStatus.DOWNLOADING
            if title:
                task.title = title
            task.progress_pct = pct
            task.speed = speed
            task.eta = eta
            task.filesize = filesize
            self._emit_progress(task)

        try:
            task.status = DownloadStatus.DOWNLOADING
            self._emit_progress(task)

            result = download_wechat_channels_sync(
                url=task.url,
                download_dir=out_dir,
                progress_callback=progress_callback,
                cancel_event=task.cancel_event,
            )

            if 'error' in result:
                err = result['error']
                if 'cancelled' in err.lower():
                    task.status = DownloadStatus.CANCELLED
                else:
                    task.status = DownloadStatus.FAILED
                    task.error = err
                task.completed_at = time.time()
                self._emit_progress(task)
                return

            # Success
            task.status = DownloadStatus.COMPLETED
            task.progress_pct = 100.0
            task.title = result.get('title', task.title)
            task.thumbnail = result.get('thumbnail')
            task.filename = result.get('filepath', '')
            task.filesize = _format_size(result.get('filesize', 0))
            task.completed_at = time.time()
            self._emit_progress(task)

        except Exception as e:
            err_msg = str(e)
            if 'cancelled' in err_msg.lower():
                task.status = DownloadStatus.CANCELLED
            else:
                task.status = DownloadStatus.FAILED
                task.error = err_msg
            task.completed_at = time.time()
            self._emit_progress(task)

    def _run_ytdlp_download(self, task: DownloadTask, request: DownloadRequest):
        """Run yt-dlp download in a worker thread."""
        try:
            from yt_dlp import YoutubeDL
        except ImportError:
            task.status = DownloadStatus.FAILED
            task.error = 'yt-dlp not found. Make sure yt-dlp is in the Python path.'
            task.completed_at = time.time()
            self._emit_progress(task)
            return

        def progress_hook(d: dict):
            if task.cancel_event.is_set():
                from yt_dlp.utils import DownloadCancelled
                raise DownloadCancelled('Download cancelled by user')

            if d['status'] == 'downloading':
                task.status = DownloadStatus.DOWNLOADING
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    task.progress_pct = round(downloaded / total * 100, 1)
                task.speed = _format_speed(d.get('speed'))
                task.eta = _format_eta(d.get('eta'))
                task.filesize = _format_size(total) if total else None
                self._emit_progress(task)

            elif d['status'] == 'finished':
                task.status = DownloadStatus.PROCESSING
                task.progress_pct = 100.0
                filename = d.get('filename', '')
                task.filename = filename
                self._emit_progress(task)

        opts = _build_ydl_opts(request, task, progress_hook)

        try:
            task.status = DownloadStatus.DOWNLOADING
            self._emit_progress(task)

            with YoutubeDL(opts) as ydl:
                # First extract info for title/thumbnail
                try:
                    info = ydl.extract_info(task.url, download=False)
                    if info:
                        task.title = info.get('title', 'Unknown')
                        task.thumbnail = info.get('thumbnail')
                        task.info_dict = info
                        self._emit_progress(task)
                except Exception:
                    pass

                # Now download
                ydl.download([task.url])

            task.status = DownloadStatus.COMPLETED
            task.progress_pct = 100.0
            task.completed_at = time.time()
            self._emit_progress(task)

        except Exception as e:
            err_msg = str(e)
            if 'cancelled' in err_msg.lower():
                task.status = DownloadStatus.CANCELLED
            elif 'cookie' in err_msg.lower() and not opts.get('cookiefile') and not opts.get('cookiesfrombrowser'):
                # Auto-fetch cookies and retry once
                task.status = DownloadStatus.DOWNLOADING
                task.error = '需要 Cookie，正在自动获取...'
                self._emit_progress(task)
                try:
                    from .auto_cookies import fetch_cookies_sync
                    result = fetch_cookies_sync(task.url)
                    if 'path' in result:
                        cookie_path = result['path']
                        logger.info(f'Auto-fetched cookies: {cookie_path}')
                        # Retry with cookies
                        opts['cookiefile'] = cookie_path
                        opts['progress_hooks'] = [progress_hook]
                        task.error = None
                        self._emit_progress(task)

                        with YoutubeDL(opts) as ydl:
                            try:
                                info = ydl.extract_info(task.url, download=False)
                                if info:
                                    task.title = info.get('title', 'Unknown')
                                    task.thumbnail = info.get('thumbnail')
                                    task.info_dict = info
                                    self._emit_progress(task)
                            except Exception:
                                pass
                            ydl.download([task.url])

                        task.status = DownloadStatus.COMPLETED
                        task.progress_pct = 100.0
                        task.completed_at = time.time()
                        self._emit_progress(task)
                        return
                    else:
                        logger.warning(f'Auto-cookie failed: {result.get("error", "unknown")}')
                except Exception as ce:
                    logger.warning(f'Auto-cookie error: {ce}')
                # Auto-cookie failed, report original error
                task.status = DownloadStatus.FAILED
                task.error = err_msg
            else:
                task.status = DownloadStatus.FAILED
                task.error = err_msg
            task.completed_at = time.time()
            self._emit_progress(task)

    def extract_info(self, url: str) -> dict:
        """Extract video info without downloading."""
        from yt_dlp import YoutubeDL
        opts = {'quiet': True, 'no_warnings': True, 'extract_flat': False}
        settings = get_settings()
        if settings.proxy:
            opts['proxy'] = settings.proxy
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                return {
                    'id': info.get('id'),
                    'title': info.get('title'),
                    'thumbnail': info.get('thumbnail'),
                    'duration': info.get('duration'),
                    'uploader': info.get('uploader'),
                    'description': (info.get('description') or '')[:500],
                    'formats': [
                        {
                            'format_id': f.get('format_id'),
                            'ext': f.get('ext'),
                            'resolution': f.get('resolution'),
                            'filesize': f.get('filesize'),
                            'vcodec': f.get('vcodec'),
                            'acodec': f.get('acodec'),
                        }
                        for f in info.get('formats', [])
                    ],
                    'subtitles': {
                        lang: [{'ext': s.get('ext')} for s in subs]
                        for lang, subs in info.get('subtitles', {}).items()
                    },
                }
            return {}


# Global singleton
download_manager = DownloadManager()
