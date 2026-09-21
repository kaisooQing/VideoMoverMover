"""Douyin video download using f2 library (solves X-Bogus/a_bogus signature problem).

This module wraps f2's Douyin API to provide working video extraction and download
for Douyin videos, bypassing yt-dlp's broken DouyinIE extractor.
"""
from __future__ import annotations
import asyncio
import logging
import os
import re
import socket
import sys
import time
import urllib.request
from typing import Callable, Optional
from urllib.error import URLError

logger = logging.getLogger(__name__)

# Check if f2 is available
_F2_AVAILABLE = False
try:
    import f2
    _F2_AVAILABLE = True
except ImportError:
    pass


def is_f2_available() -> bool:
    """Check if f2 library is installed and importable."""
    return _F2_AVAILABLE


# f2 library path - skip in frozen mode (f2 is bundled)
if getattr(sys, 'frozen', False):
    _F2_LIB_PATH = None
else:
    _F2_LIB_PATH = os.path.join(os.path.dirname(__file__), '..', 'libs')
    if _F2_LIB_PATH not in sys.path:
        sys.path.insert(0, _F2_LIB_PATH)

# Cookie directory - in frozen mode, place next to the EXE; in dev mode, relative to this file
if getattr(sys, 'frozen', False):
    COOKIE_DIR = os.path.join(os.path.dirname(sys.executable), 'cookies')
else:
    COOKIE_DIR = os.path.join(os.path.dirname(__file__), '..', 'cookies')
os.makedirs(COOKIE_DIR, exist_ok=True)


def is_douyin_url(url: str) -> bool:
    """Check if the URL is a Douyin URL."""
    return bool(re.search(r'douyin\.com|iesdouyin\.com', url, re.IGNORECASE))


def _read_cookie_str(cookie_file: Optional[str] = None) -> str:
    """Read cookies from a Netscape format file and return as a cookie string."""
    if cookie_file and os.path.exists(cookie_file):
        target = cookie_file
    else:
        # Find the latest auto-fetched douyin cookie file
        files = [f for f in os.listdir(COOKIE_DIR) if f.startswith('douyin_auto_') and f.endswith('.txt')]
        if not files:
            return ''
        files.sort(reverse=True)
        target = os.path.join(COOKIE_DIR, files[0])

    cookie_str = ''
    with open(target, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split('\t')
            if len(parts) >= 7:
                cookie_str += f'{parts[5]}={parts[6]}; '
    return cookie_str.rstrip('; ')


async def fetch_douyin_info(url: str, cookie_file: Optional[str] = None) -> dict:
    """
    Fetch Douyin video info using f2 library.

    Returns dict with: aweme_id, title, author, thumbnail, duration, video_urls
    """
    from f2.apps.douyin.utils import AwemeIdFetcher
    from f2.apps.douyin.crawler import DouyinCrawler
    from f2.apps.douyin.model import PostDetail
    from f2.apps.douyin.filter import PostDetailFilter

    cookie_str = _read_cookie_str(cookie_file)
    if not cookie_str:
        return {'error': 'No Douyin cookies available. Please upload or auto-fetch cookies first.'}

    kwargs = {
        'cookie': cookie_str,
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0',
            'Referer': 'https://www.douyin.com/',
        },
        'proxies': {"http://": None, "https://": None},
    }

    # Resolve aweme_id from URL
    aweme_id = await AwemeIdFetcher.get_aweme_id(url)

    # Fetch video detail
    async with DouyinCrawler(kwargs) as crawler:
        params = PostDetail(aweme_id=aweme_id)
        response = await crawler.fetch_post_detail(params)

    if not isinstance(response, dict):
        return {'error': f'Unexpected response type: {type(response)}'}

    status = response.get('status_code', -1)
    if status != 0:
        return {'error': f'API returned status_code: {status}'}

    video = PostDetailFilter(response)

    # aweme_type: 0=video, 2=image_post, 68=image_post, 55/61/107/151=other video types
    aweme_type = video.aweme_type
    images = video.images or []
    # Filter out None/empty entries from images
    images = [img for img in images if img]

    # Extract bit_rate data for best quality selection
    # The raw response contains bit_rate list with multiple quality levels
    bit_rate_data = []
    try:
        raw_aweme = response.get('aweme_detail', {}) or response
        bit_rate_list = raw_aweme.get('video', {}).get('bit_rate', [])
        if bit_rate_list:
            bit_rate_data = bit_rate_list
    except Exception:
        pass

    return {
        'aweme_id': video.aweme_id,
        'aweme_type': aweme_type,
        'title': video.desc_raw or video.desc,
        'author': video.nickname_raw or video.nickname,
        'thumbnail': video.cover,
        'duration': (video.duration or 0) / 1000 if video.duration else None,
        'video_urls': video.video_play_addr or [],
        'images': images,
        'bit_rate': bit_rate_data,
    }


async def _download_douyin_images(
    info: dict,
    images: list,
    download_dir: str,
    cookie_file: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[object] = None,
) -> dict:
    """Download all images from a Douyin image post (图文)."""
    title = info.get('title', 'untitled') or 'untitled'
    safe_title = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', title)[:80].strip()
    if not safe_title:
        safe_title = f'douyin_{info.get("aweme_id", "post")}'

    # Create a subfolder for the image post
    post_dir = os.path.join(download_dir, safe_title)
    os.makedirs(post_dir, exist_ok=True)

    cookie_str = _read_cookie_str(cookie_file)
    total_images = len(images)
    downloaded_files = []

    logger.info(f'Downloading {total_images} images from Douyin image post: {title}')

    for idx, img_url in enumerate(images):
        if cancel_event and cancel_event.is_set():
            # Clean up on cancel
            for f in downloaded_files:
                if os.path.exists(f):
                    os.remove(f)
            return {'error': 'cancelled'}

        # Determine extension from URL or default to jpg
        ext = 'jpg'
        if '.png' in img_url.lower():
            ext = 'png'
        elif '.webp' in img_url.lower():
            ext = 'webp'

        filepath = os.path.join(post_dir, f'{idx + 1:03d}.{ext}')

        if progress_callback:
            pct = round(idx / total_images * 100, 1)
            progress_callback(f'{title} ({idx + 1}/{total_images})', pct, None, None, f'{total_images} 张图片')

        try:
            req = urllib.request.Request(img_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0',
                'Referer': 'https://www.douyin.com/',
                'Cookie': cookie_str,
            })
            resp = urllib.request.urlopen(req, timeout=60)
            with open(filepath, 'wb') as f:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
            resp.close()

            filesize = os.path.getsize(filepath)
            downloaded_files.append(filepath)
            logger.info(f'  Image {idx + 1}/{total_images}: {filepath} ({filesize} bytes)')

        except Exception as e:
            logger.warning(f'  Failed to download image {idx + 1}: {e}')

    if not downloaded_files:
        return {'error': 'Failed to download any images'}

    if progress_callback:
        progress_callback(title, 100.0, None, None, f'{total_images} 张图片')

    total_size = sum(os.path.getsize(f) for f in downloaded_files)
    return {
        'title': title,
        'filepath': post_dir,
        'filesize': total_size,
        'author': info.get('author', ''),
        'thumbnail': info.get('thumbnail'),
        'type': 'images',
        'image_count': len(downloaded_files),
    }


async def download_douyin_video(
    url: str,
    download_dir: str,
    cookie_file: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[object] = None,
) -> dict:
    """
    Download a Douyin video using f2 library.

    Args:
        url: Douyin URL (share URL or full URL)
        download_dir: Directory to save the video
        cookie_file: Optional path to cookie file
        progress_callback: Optional callable(title, pct, speed, eta, filesize)
        cancel_event: Optional threading.Event for cancellation

    Returns dict with: title, filepath, filesize, author, thumbnail
    """
    info = await fetch_douyin_info(url, cookie_file)
    if 'error' in info:
        return info

    aweme_type = info.get('aweme_type', 0)
    video_urls = info.get('video_urls', [])
    images = info.get('images', [])

    # Image post (图文): aweme_type 2 or 68
    if aweme_type in (2, 68) and images and not video_urls:
        return await _download_douyin_images(info, images, download_dir, cookie_file, progress_callback, cancel_event)

    # Select best quality video URL
    # Strategy: use bit_rate data to find the highest bitrate (best quality) URL
    bit_rate_data = info.get('bit_rate', [])
    video_url = None
    quality_info = ''

    if bit_rate_data:
        # Sort by bit_rate descending to get highest quality first
        sorted_br = sorted(bit_rate_data, key=lambda x: x.get('bit_rate', 0), reverse=True)
        for br in sorted_br:
            urls = br.get('play_addr', {}).get('url_list', [])
            if urls:
                video_url = urls[0]
                gear_name = br.get('gear_name', '')
                bitrate = br.get('bit_rate', 0)
                quality_info = f'{gear_name} ({bitrate // 1000}kbps)' if gear_name else f'{bitrate // 1000}kbps'
                logger.info(f'Selected best quality: {quality_info}')
                break

    if not video_url and video_urls:
        # Fallback to first play_addr URL (usually no-watermark)
        video_url = video_urls[0]
        quality_info = 'default'

    if not video_url:
        return {'error': 'No video URLs found'}

    title = info.get('title', 'untitled') or 'untitled'
    safe_title = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', title)[:80].strip()
    if not safe_title:
        safe_title = f'douyin_{info.get("aweme_id", "video")}'

    os.makedirs(download_dir, exist_ok=True)
    filepath = os.path.join(download_dir, f'{safe_title}.mp4')

    # Avoid overwriting
    if os.path.exists(filepath):
        base, ext = os.path.splitext(filepath)
        filepath = f'{base}_{int(time.time())}{ext}'

    cookie_str = _read_cookie_str(cookie_file)

    # Report initial progress
    if progress_callback:
        progress_callback(title, 0, None, None, None)

    # Download with progress
    req = urllib.request.Request(video_url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0',
        'Referer': 'https://www.douyin.com/',
        'Cookie': cookie_str,
    })

    _MAX_RETRIES = 2
    _RETRY_DELAY = 2

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            total_size = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            start_time = time.time()

            with open(filepath, 'wb') as f:
                while True:
                    if cancel_event and cancel_event.is_set():
                        resp.close()
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return {'error': 'cancelled'}

                    chunk = resp.read(1024 * 256)  # 256KB chunks
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        pct = round(downloaded / total_size * 100, 1)
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        speed_str = f'{speed / 1024 / 1024:.1f} MB/s' if speed > 1024 * 1024 else f'{speed / 1024:.0f} KB/s'
                        eta = int((total_size - downloaded) / speed) if speed > 0 else None
                        eta_str = f'{eta}s' if eta and eta < 3600 else (f'{eta // 60}m' if eta else None)
                        total_str = f'{total_size / 1024 / 1024:.1f} MB'
                        progress_callback(title, pct, speed_str, eta_str, total_str)

            resp.close()

            filesize = os.path.getsize(filepath)
            return {
                'title': title,
                'filepath': filepath,
                'filesize': filesize,
                'author': info.get('author', ''),
                'thumbnail': info.get('thumbnail'),
            }

        except (socket.timeout, TimeoutError, URLError, OSError) as e:
            if 'timed out' in str(e).lower() or isinstance(e, (socket.timeout, TimeoutError)):
                logger.warning(f'Download timed out (attempt {attempt + 1}/{_MAX_RETRIES + 1}): {e}')
                if attempt < _MAX_RETRIES:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    time.sleep(_RETRY_DELAY)
                    continue
            if os.path.exists(filepath):
                os.remove(filepath)
            return {'error': str(e)}

    return {'error': 'All download attempts failed'}


def download_douyin_sync(
    url: str,
    download_dir: str,
    cookie_file: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[object] = None,
) -> dict:
    """Synchronous wrapper for download_douyin_video."""
    try:
        return asyncio.run(
            download_douyin_video(url, download_dir, cookie_file, progress_callback, cancel_event)
        )
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                download_douyin_video(url, download_dir, cookie_file, progress_callback, cancel_event)
            )
            return future.result(timeout=600)
