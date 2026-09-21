"""Android backend utilities - shared between main.py and start_server.py.

This module contains Android-specific helpers that are NOT shared with PC backend.
PC and Android backends are intentionally separate.
"""
from __future__ import annotations
import logging
import os
import re
import sys
import json
import shutil
import time
import urllib.request
import http.cookiejar
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

_ANDROID_CONTEXT = None


def _get_android_context():
    """Get Android Context - stored by Java during start()."""
    global _ANDROID_CONTEXT
    if _ANDROID_CONTEXT is not None:
        return _ANDROID_CONTEXT
    try:
        import start_server
        ctx = start_server._get_android_context()
        if ctx is not None:
            return ctx
    except Exception:
        pass
    try:
        from java import jclass
        _ANDROID_CONTEXT = jclass("com.chaquo.python.Python").getInstance().getPlatform().getContext()
    except Exception:
        pass
    return _ANDROID_CONTEXT


def move_to_dcim(file_path: str) -> Optional[str]:
    """Move a downloaded file or folder to DCIM/VideoMover so it appears in gallery.

    For single files: move to DCIM/VideoMover.
    For folders (image posts): move the whole folder to DCIM/VideoMover.
    Returns the new path on success, or None on failure.
    """
    if not file_path or not os.path.exists(file_path):
        return None

    dcim_dir = _ensure_dcim_videomover()
    if not dcim_dir:
        logger.warning("Cannot create DCIM/VideoMover directory")
        return None

    try:
        if os.path.isdir(file_path):
            # Folder: move entire folder to DCIM/VideoMover
            folder_name = os.path.basename(file_path)
            dest = os.path.join(dcim_dir, folder_name)
            if os.path.exists(dest):
                dest = os.path.join(dcim_dir, folder_name + '_' + str(int(time.time())))
            shutil.move(file_path, dest)
            logger.info(f"Moved folder to DCIM/VideoMover: {dest}")
            return dest
        else:
            # Single file: move to DCIM/VideoMover
            filename = os.path.basename(file_path)
            dest = os.path.join(dcim_dir, filename)
            if os.path.exists(dest):
                base, ext = os.path.splitext(filename)
                dest = os.path.join(dcim_dir, base + '_' + str(int(time.time())) + ext)
            shutil.move(file_path, dest)
            logger.info(f"Moved file to DCIM/VideoMover: {dest}")
            return dest
    except Exception as e:
        logger.warning(f"move_to_dcim failed: {e}")
        return None


def scan_downloaded_file(file_path: str) -> None:
    """Trigger MediaScanner so the file appears in gallery immediately.
    Works for any public directory (DCIM, Download, etc.)."""
    if not file_path or not os.path.exists(file_path):
        return
    try:
        from java import jclass
        context = _get_android_context()
        if context is None:
            return
        MediaStoreHelper = jclass("com.ytdlp.webui.MediaStoreHelper")
        MediaStoreHelper.scanFile(context, file_path)
        logger.info(f"MediaScanner triggered for: {file_path}")
    except Exception as e:
        logger.warning(f"scan_downloaded_file failed: {e}")


def _ensure_dcim_videomover() -> Optional[str]:
    """Ensure DCIM/VideoMover directory exists and is writable. Return path or None."""
    try:
        dcim_dir = "/storage/emulated/0/DCIM/VideoMover"
        os.makedirs(dcim_dir, exist_ok=True)
        test_file = os.path.join(dcim_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return dcim_dir
    except Exception as e:
        logger.warning(f"DCIM/VideoMover not writable: {e}")
        # Try MediaStore approach
        try:
            from java import jclass
            context = _get_android_context()
            if context:
                env = jclass("android.os.Environment")
                dcim = env.getExternalStoragePublicDirectory(env.DIRECTORY_DCIM)
                path = str(dcim.getAbsolutePath()) + "/VideoMover"
                os.makedirs(path, exist_ok=True)
                test_file = os.path.join(path, ".write_test")
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                return path
        except Exception as e2:
            logger.warning(f"DCIM/VideoMover via Java also failed: {e2}")
        return None


def _get_download_dir() -> str:
    """Get the download directory.

    Directly use Download/VideoMover so files stay in one place.
    """
    try:
        context = _get_android_context()
        if context is None:
            return "/storage/emulated/0/Download/VideoMover"

        # Try 1: Public Download directory (always writable)
        try:
            from java import jclass
            env = jclass("android.os.Environment")
            public_dl = env.getExternalStoragePublicDirectory(env.DIRECTORY_DOWNLOADS)
            path = str(public_dl.getAbsolutePath()) + "/VideoMover"
            os.makedirs(path, exist_ok=True)
            logger.info(f"Using public Download directory: {path}")
            return path
        except Exception as e:
            logger.warning(f"Download dir not accessible: {e}")

        # Try 2: App-specific external storage
        ext_files = context.getExternalFilesDir(None)
        if ext_files:
            path = str(ext_files.getAbsolutePath()) + "/Downloads"
            os.makedirs(path, exist_ok=True)
            logger.info(f"Using app external storage: {path}")
            return path

        # Try 3: App internal storage
        path = str(context.getFilesDir().getAbsolutePath()) + "/Downloads"
        os.makedirs(path, exist_ok=True)
        logger.info(f"Using internal storage: {path}")
        return path
    except Exception:
        return "/storage/emulated/0/Download/VideoMover"


def _extract_url(text: str) -> str:
    """Extract URL from share text like Douyin/Bilibili clipboard content."""
    text = text.strip()
    if re.match(r'^https?://\S+$', text):
        return text
    url_pattern = r'https?://[^\s<>\[\](){}\\一-\u9fff]+'
    matches = re.findall(url_pattern, text)
    if matches:
        url = matches[0].rstrip('/')
        url = re.sub(r'[\uff0c\u3002\uff01\uff1f\u3001\uff1b\uff1a\]\}]+$', '', url)
        return url
    return text


def _detect_platform(url: str) -> str:
    """Detect which video platform a URL belongs to."""
    url_lower = url.lower()
    if 'douyin.com' in url_lower or 'v.douyin' in url_lower:
        return 'douyin'
    elif 'bilibili.com' in url_lower or 'b23.tv' in url_lower:
        return 'bilibili'
    elif 'xiaohongshu.com' in url_lower or 'xhslink' in url_lower:
        return 'xiaohongshu'
    elif 'kuaishou.com' in url_lower or 'v.kuaishou' in url_lower:
        return 'kuaishou'
    elif 'weixin.qq.com' in url_lower or 'channels.weixin.qq.com' in url_lower:
        return 'wechat_channels'
    return 'other'


def _normalize_platform_url(url: str):
    """Resolve short URLs and convert to yt-dlp compatible format.
    Returns (normalized_url, platform).
    """
    import urllib.request
    from urllib.parse import urlparse, parse_qs

    platform = _detect_platform(url)

    if platform == 'douyin':
        return url, platform

    needs_resolve = any(d in url.lower() for d in [
        'v.kuaishou.com', 'xhslink.com', 'b23.tv',
        'xiaohongshu.com/explore/', 'xhslink'
    ])

    if not needs_resolve:
        return url, platform

    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        resolved = resp.url
        resp.close()
        logger.info(f"Resolved URL: {url} -> {resolved}")
    except Exception as e:
        logger.warning(f"URL resolution failed: {e}")
        return url, platform

    if platform == 'kuaishou':
        parsed = urlparse(resolved)
        qs = parse_qs(parsed.query)
        photo_id = qs.get('photoId', [None])[0]

        if photo_id:
            resolved = f'https://v.kuaishou.com/short-video/{photo_id}'
            logger.info(f"Kuaishou URL from photoId: {resolved}")
        elif 'kuaishou.com' in resolved:
            resolved = resolved.replace('www.kuaishou.com', 'v.kuaishou.com')
            if '?' in resolved:
                resolved = resolved.split('?')[0]
            logger.info(f"Kuaishou URL normalized: {resolved}")
        else:
            m = re.search(r'/([a-z0-9]{20,})', parsed.path)
            if m:
                resolved = f'https://v.kuaishou.com/short-video/{m.group(1)}'
                logger.info(f"Kuaishou URL from path: {resolved}")
            else:
                logger.warning(f"Could not normalize Kuaishou URL: {resolved}")

    elif platform == 'xiaohongshu':
        m = re.search(r'/(?:explore|discovery/item)/([a-f0-9]+)', resolved)
        if m:
            resolved = f'https://www.xiaohongshu.com/explore/{m.group(1)}'
            logger.info(f"Xiaohongshu URL normalized: {resolved}")

    elif platform == 'bilibili':
        m = re.search(r'/(BV[a-zA-Z0-9]+)', resolved)
        if m:
            resolved = f'https://www.bilibili.com/video/{m.group(1)}'
            logger.info(f"Bilibili URL normalized: {resolved}")

    return resolved, platform


def _resolve_douyin_url(url: str):
    """Resolve a Douyin short URL to get the aweme_id."""
    import urllib.request

    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        final_url = resp.url
        resp.close()
        logger.info(f"Resolved Douyin URL: {url} -> {final_url}")
    except Exception as e:
        logger.warning(f"URL resolution failed: {e}")
        final_url = url

    # 1) Known path patterns: /video/, /note/, /slides/ (image posts),
    #    optionally under a /share/ prefix (e.g. iesdouyin.com/share/slides/123)
    m = re.search(r'/(?:share/)?(?:video|note|slides)/(\d+)', final_url)
    if m:
        return m.group(1), final_url

    # 2) Query-param fallback: some share links carry aweme_id in the query string
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(final_url).query)
    if qs.get('aweme_id'):
        return qs['aweme_id'][0], final_url

    # 3) Generic fallback: an aweme_id is a ~19-digit number appearing as a path segment
    m = re.search(r'/(\d{15,20})(?:[/?]|$)', final_url)
    if m:
        return m.group(1), final_url

    return None, final_url


def _fetch_douyin_ttwid():
    """Fetch a real ttwid cookie from Douyin's registration endpoint."""
    import urllib.request
    import http.cookiejar

    ttwid_url = "https://ttwid.bytedance.com/ttwid/union/register/"
    ttwid_body = json.dumps({
        "region": "cn", "aid": 1768, "needFid": False,
        "service": "www.ixigua.com",
        "migrate_info": {"ticket": "", "source": "node"},
        "cbUrlProtocol": "https", "union": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        ttwid_url, data=ttwid_body,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        cookie_jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        resp = opener.open(req, timeout=10)
        resp.close()
        for cookie in cookie_jar:
            if cookie.name == "ttwid":
                return cookie.value
    except Exception as e:
        logger.warning(f"Failed to fetch ttwid: {e}")
    return None


# Error log helpers
_ERROR_LOG_PATH = "/data/data/com.ytdlp.webui/files/server_error.log"


def _write_error_log(msg: str):
    try:
        os.makedirs(os.path.dirname(_ERROR_LOG_PATH), exist_ok=True)
        with open(_ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _log(msg: str):
    """Log to both logger and error log file."""
    logger.info(msg)
    _write_error_log(msg)


def _is_android() -> bool:
    return "ANDROID_ROOT" in os.environ or hasattr(sys, "android_api_level")
