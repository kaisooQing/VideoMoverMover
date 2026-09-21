"""yt-dlp downloader wrapper with platform routing."""
from __future__ import annotations
import logging
import os
import traceback

from yt_dlp import YoutubeDL

from ..utils import _detect_platform, _extract_url, _normalize_platform_url

from .bilibili import _download_bilibili_direct
from .douyin import _download_douyin_direct
from .kuaishou import _download_kuaishou_direct
from .xiaohongshu import _download_xiaohongshu_direct
from .wechat_channels import _download_wechat_channels_direct

logger = logging.getLogger(__name__)


def _run_ytdlp_download(task, url, download_dir):
    """Run yt-dlp download in background thread with platform routing."""
    try:
        # Extract clean URL from share text
        clean_url = _extract_url(url)
        task['url'] = clean_url
        logger.info(f"[Task {task['id']}] URL extracted: '{url}' -> '{clean_url}'")

        task['status'] = 'starting'
        task['title'] = '正在初始化...'

        # Detect platform and normalize URL
        platform = _detect_platform(clean_url)
        logger.info(f"[Task {task['id']}] Platform: {platform}")

        # Douyin: use direct download (yt-dlp doesn't work for Douyin)
        if platform == 'douyin':
            logger.info(f"[Task {task['id']}] Using direct Douyin downloader")
            _download_douyin_direct(task, clean_url, download_dir)
            return

        # Kuaishou: use direct download (yt-dlp KuaishouIE is broken)
        if platform == 'kuaishou':
            logger.info(f"[Task {task['id']}] Using direct Kuaishou downloader")
            _download_kuaishou_direct(task, clean_url, download_dir)
            return

        # Xiaohongshu: use direct download (yt-dlp doesn't support image posts)
        if platform == 'xiaohongshu':
            logger.info(f"[Task {task['id']}] Using direct Xiaohongshu downloader")
            _download_xiaohongshu_direct(task, clean_url, download_dir)
            return

        # Bilibili: use direct download (yt-dlp gets 412 errors)
        if platform == 'bilibili':
            logger.info(f"[Task {task['id']}] Using direct Bilibili downloader")
            _download_bilibili_direct(task, clean_url, download_dir)
            return

        # WeChat Channels (视频号): use online parser API
        if platform == 'wechat_channels':
            logger.info(f"[Task {task['id']}] Using WeChat Channels downloader")
            _download_wechat_channels_direct(task, clean_url, download_dir)
            return

        # Other platforms: resolve short URL and normalize for yt-dlp
        normalized_url, platform = _normalize_platform_url(clean_url)
        if normalized_url != clean_url:
            task['url'] = normalized_url
            logger.info(f"[Task {task['id']}] URL normalized: '{clean_url}' -> '{normalized_url}'")

        # Import yt-dlp
        logger.info(f"[Task {task['id']}] Importing yt_dlp...")

        def progress_hook(d):
            if d['status'] == 'downloading':
                task['status'] = 'downloading'
                pct_str = d.get('_percent_str', '0%')
                try:
                    pct = float(pct_str.rstrip('%'))
                except:
                    pct = 0.0
                task['progress_pct'] = pct
                task['speed'] = d.get('_speed_str')
                task['eta'] = d.get('_eta_str')
                task['filesize'] = d.get('_total_bytes_str')
            elif d['status'] == 'finished':
                task['status'] = 'processing'
                task['progress_pct'] = 100.0

        ydl_opts = {
            'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'quiet': False,
            'no_warnings': False,
        }

        task['title'] = '正在提取视频信息...'
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(normalized_url, download=True)
            if info:
                task['title'] = info.get('title', 'Unknown')
                task['filename'] = ydl.prepare_filename(info)
                task['thumbnail'] = info.get('thumbnail')

        task['status'] = 'completed'
        task['progress_pct'] = 100.0
        task['completed_at'] = time.time()
        logger.info(f"[Task {task['id']}] Download completed: {task['title']}")

    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.error(f"[Task {task['id']}] Download failed: {error_msg}")
        logger.error(traceback.format_exc())
        task['status'] = 'failed'
        task['error'] = error_msg
        task['completed_at'] = time.time()
