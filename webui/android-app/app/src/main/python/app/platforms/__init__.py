"""Platform-specific downloaders for Android backend.

Each module handles a specific video platform using Android-compatible methods
(no Playwright, no browser automation).
"""
from .douyin import _download_douyin_direct
from .kuaishou import _download_kuaishou_direct
from .xiaohongshu import _download_xiaohongshu_direct
from .bilibili import _download_bilibili_direct
from .ytdlp import _run_ytdlp_download

__all__ = [
    '_download_douyin_direct',
    '_download_kuaishou_direct',
    '_download_xiaohongshu_direct',
    '_download_bilibili_direct',
    '_run_ytdlp_download',
]
