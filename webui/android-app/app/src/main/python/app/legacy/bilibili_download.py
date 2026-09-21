"""Bilibili (B站) video download module.

Uses Playwright to bypass 412 Precondition Failed errors and extract
video/audio stream URLs from __playinfo__. Downloads DASH streams
separately and merges with FFmpeg.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from typing import Callable, Optional
from urllib.error import URLError

logger = logging.getLogger(__name__)

_DESKTOP_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0'
)

# FFmpeg location
_FFMPEG = 'ffmpeg'


def is_bilibili_url(url: str) -> bool:
    """Check if the URL is a Bilibili URL."""
    return bool(re.search(r'bilibili\.com|b23\.tv|bili[a-z]*\.com', url, re.IGNORECASE))


def _resolve_short_url(url: str) -> str:
    """Resolve a Bilibili short URL (b23.tv) to its full form."""
    if 'b23.tv' not in url:
        return url
    req = urllib.request.Request(url, headers={
        'User-Agent': _DESKTOP_UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.bilibili.com/',
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        final_url = resp.url
        resp.close()
        # Clean up the URL - extract just the video part
        match = re.search(r'(https://www\.bilibili\.com/video/[^?&]+)', final_url)
        if match:
            return match.group(1).rstrip('/') + '/'
        return final_url
    except Exception as e:
        logger.warning(f'Short URL resolve failed: {e}')
        return url


async def _extract_playinfo(page_url: str) -> dict:
    """Use Playwright to extract __playinfo__ and metadata from a Bilibili page."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel='msedge',
            headless=True,
            args=['--disable-blink-features=AutomationControlled'],
        )
        context = await browser.new_context(
            user_agent=_DESKTOP_UA,
            locale='zh-CN',
        )
        page = await context.new_page()

        try:
            # Visit homepage first for cookies
            await page.goto('https://www.bilibili.com/', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)

            # Visit video page
            await page.goto(page_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)

            # Extract __playinfo__
            playinfo = await page.evaluate('''() => {
                if (window.__playinfo__) return window.__playinfo__;
                return null;
            }''')

            # Fallback: extract __playinfo__ from page source via regex
            if not playinfo:
                content = await page.content()
                pi_match = re.search(
                    r'window\.__playinfo__\s*=\s*(\{.+?\})\s*;?\s*</script>',
                    content, re.DOTALL
                )
                if pi_match:
                    try:
                        playinfo = json.loads(pi_match.group(1))
                    except json.JSONDecodeError:
                        pass

            # Extract metadata from __INITIAL_STATE__
            metadata = await page.evaluate('''() => {
                if (window.__INITIAL_STATE__) {
                    const vd = window.__INITIAL_STATE__.videoData;
                    if (vd) return {
                        title: vd.title,
                        desc: vd.desc,
                        owner: vd.owner?.name,
                        pic: vd.pic,
                        duration: vd.duration,
                        aid: vd.aid,
                        bvid: vd.bvid,
                    };
                }
                return null;
            }''')

            # Fallback: extract metadata from page source
            if not metadata:
                content = await page.content()
                is_match = re.search(
                    r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;?\s*</script>',
                    content, re.DOTALL
                )
                if is_match:
                    try:
                        state = json.loads(is_match.group(1))
                        vd = state.get('videoData', {})
                        if vd:
                            metadata = {
                                'title': vd.get('title', ''),
                                'desc': vd.get('desc', ''),
                                'owner': (vd.get('owner') or {}).get('name', ''),
                                'pic': vd.get('pic', ''),
                                'duration': vd.get('duration'),
                                'aid': vd.get('aid'),
                                'bvid': vd.get('bvid'),
                            }
                    except json.JSONDecodeError:
                        pass

            # Get cookies for download
            cookies = await context.cookies()
            cookie_str = '; '.join(f'{c["name"]}={c["value"]}' for c in cookies)

            return {
                'playinfo': playinfo,
                'metadata': metadata,
                'cookie_str': cookie_str,
            }
        finally:
            await context.close()
            await browser.close()


_MAX_RETRIES = 2
_RETRY_DELAY = 2


def _download_stream_with_fallback(url: str, filepath: str, cookie_str: str,
                                     backup_urls: list = None,
                                     progress_callback: Optional[Callable] = None,
                                     label: str = '',
                                     cancel_event: Optional[object] = None) -> bool:
    """Download a single stream, trying the main URL first, then backup URLs on failure."""
    # Build URL list: main URL + backup URLs
    urls_to_try = [url] + (backup_urls or [])

    for i, try_url in enumerate(urls_to_try):
        if cancel_event and cancel_event.is_set():
            return False

        source_label = f'{label} (CDN {i + 1})' if len(urls_to_try) > 1 else label
        if i > 0:
            logger.info(f'Trying backup URL {i + 1}/{len(urls_to_try) - 1} for {label}')

        if _download_stream(try_url, filepath, cookie_str, progress_callback,
                             source_label, cancel_event):
            return True

        # Clean up partial file before trying next URL
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

    return False


def _download_stream(url: str, filepath: str, cookie_str: str,
                     progress_callback: Optional[Callable] = None,
                     label: str = '',
                     cancel_event: Optional[object] = None) -> bool:
    """Download a single stream (video or audio) to file with automatic retry on any failure."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': _DESKTOP_UA,
                'Referer': 'https://www.bilibili.com/',
                'Cookie': cookie_str,
                'Origin': 'https://www.bilibili.com',
            })
            resp = urllib.request.urlopen(req, timeout=60)

            # Validate response is binary video/audio (not HTML error page)
            content_type = resp.headers.get('Content-Type', '').lower().split(';')[0].strip()
            if content_type and ('html' in content_type or 'json' in content_type):
                resp.close()
                logger.warning(f'Invalid Content-Type (attempt {attempt + 1}): {content_type}')
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
                    continue
                return False

            total_size = int(resp.headers.get('Content-Length', 0))
            downloaded = 0
            start_time = time.time()

            with open(filepath, 'wb') as f:
                while True:
                    if cancel_event and cancel_event.is_set():
                        resp.close()
                        return False

                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size > 0:
                        pct = round(downloaded / total_size * 100, 1)
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        speed_str = f'{speed / 1024 / 1024:.1f} MB/s' if speed > 1024 * 1024 else f'{speed / 1024:.0f} KB/s'
                        total_str = f'{total_size / 1024 / 1024:.1f} MB'
                        progress_callback(f'{label}', pct, speed_str, None, total_str)

            resp.close()

            # Validate file size
            actual_size = os.path.getsize(filepath)
            if total_size > 0 and abs(actual_size - total_size) > 1024:
                logger.warning(f'File size mismatch: expected {total_size}, got {actual_size}')
                if attempt < _MAX_RETRIES:
                    os.remove(filepath)
                    time.sleep(_RETRY_DELAY)
                    continue
                return False

            return True

        except (socket.timeout, TimeoutError, URLError, OSError, Exception) as e:
            # Log and retry on ANY failure (timeout, 403, 412, connection reset, etc.)
            error_str = str(e).lower()
            is_timeout = 'timed out' in error_str or isinstance(e, (socket.timeout, TimeoutError))
            category = 'timeout' if is_timeout else 'error'
            logger.warning(f'Stream download {category} (attempt {attempt + 1}/{_MAX_RETRIES + 1}): {e}')
            if attempt < _MAX_RETRIES:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
                time.sleep(_RETRY_DELAY)
                continue
            return False

    return False


def _merge_av(video_path: str, audio_path: str, output_path: str) -> bool:
    """Merge video and audio streams using FFmpeg."""
    try:
        cmd = [
            _FFMPEG, '-y',
            '-i', video_path,
            '-i', audio_path,
            '-c', 'copy',
            '-movflags', '+faststart',
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                                encoding='utf-8', errors='replace')
        return result.returncode == 0
    except Exception as e:
        logger.error(f'FFmpeg merge failed: {e}')
        return False


def download_bilibili_sync(
    url: str,
    download_dir: str,
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[object] = None,
) -> dict:
    """
    Download a Bilibili video synchronously.

    Uses Playwright to extract stream URLs, downloads video+audio separately,
    then merges with FFmpeg.
    """
    # Resolve short URL
    if 'b23.tv' in url:
        url = _resolve_short_url(url)
        logger.info(f'Resolved to: {url}')

    if progress_callback:
        progress_callback('正在获取视频信息...', 0, None, None, None)

    # Extract playinfo via Playwright
    try:
        result = asyncio.run(_extract_playinfo(url))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, _extract_playinfo(url))
            result = future.result(timeout=120)
    except Exception as e:
        return {'error': f'Playwright extraction error: {e}'}

    playinfo = result.get('playinfo')
    metadata = result.get('metadata')
    cookie_str = result.get('cookie_str', '')

    logger.info(f'Extract result keys: {list(result.keys())}')
    logger.info(f'playinfo type: {type(playinfo)}, truthy: {bool(playinfo)}')
    logger.info(f'metadata: {metadata}')
    logger.info(f'cookie_str length: {len(cookie_str)}')

    if not playinfo or not playinfo.get('data'):
        logger.error(f'Extraction failed. playinfo={playinfo}')
        return {'error': 'Failed to extract video info from Bilibili page'}

    data = playinfo['data']
    title = (metadata or {}).get('title', '') or 'untitled'
    author = (metadata or {}).get('owner', '')

    safe_title = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', title)[:80].strip()
    if not safe_title:
        safe_title = f'bilibili_video_{int(time.time())}'

    os.makedirs(download_dir, exist_ok=True)
    output_path = os.path.join(download_dir, f'{safe_title}.mp4')

    # Avoid overwriting
    if os.path.exists(output_path):
        base, ext = os.path.splitext(output_path)
        output_path = f'{base}_{int(time.time())}{ext}'

    dash = data.get('dash')
    durl = data.get('durl')

    if dash:
        # DASH format: separate video + audio
        videos = dash.get('video', [])
        audios = dash.get('audio', [])

        if not videos:
            return {'error': 'No video streams found'}

        # Select best video stream by bandwidth (highest = best quality)
        # Each stream has: id (quality level), bandwidth, width, height, codecs
        videos_sorted = sorted(videos, key=lambda x: x.get('bandwidth', 0), reverse=True)
        video_stream = videos_sorted[0]
        video_url = video_stream.get('baseUrl') or video_stream.get('base_url')
        video_quality = f'{video_stream.get("width", "?")}x{video_stream.get("height", "?")}'
        logger.info(f'Selected best video quality: {video_quality}, bandwidth={video_stream.get("bandwidth", 0) // 1000}kbps')

        # Temp files
        video_tmp = output_path + '.video.m4s'
        audio_tmp = output_path + '.audio.m4s'

        # Extract backup URLs from video stream
        video_backup = video_stream.get('backupUrl') or video_stream.get('backup_url') or []

        try:
            # Download video stream (with backup CDN fallback)
            if progress_callback:
                quality = video_stream.get('width', 0)
                progress_callback(f'{title} (视频)', 0, None, None, None)

            if not _download_stream_with_fallback(video_url, video_tmp, cookie_str,
                                                   video_backup, progress_callback,
                                                   f'{safe_title} (视频)', cancel_event):
                return {'error': 'cancelled' if cancel_event and cancel_event.is_set() else 'Video stream download failed'}

            # Download audio stream - select best quality by bandwidth
            if audios:
                audios_sorted = sorted(audios, key=lambda x: x.get('bandwidth', 0), reverse=True)
                audio_stream = audios_sorted[0]
                audio_url = audio_stream.get('baseUrl') or audio_stream.get('base_url')
                audio_backup = audio_stream.get('backupUrl') or audio_stream.get('backup_url') or []
                logger.info(f'Selected best audio: bandwidth={audio_stream.get("bandwidth", 0) // 1000}kbps')

                if progress_callback:
                    progress_callback(f'{safe_title} (音频)', 0, None, None, None)

                if not _download_stream_with_fallback(audio_url, audio_tmp, cookie_str,
                                                       audio_backup, progress_callback,
                                                       f'{safe_title} (音频)', cancel_event):
                    return {'error': 'cancelled' if cancel_event and cancel_event.is_set() else 'Audio stream download failed'}

                # Merge
                if progress_callback:
                    progress_callback(f'{safe_title} (合并中...)', 95, None, None, None)

                if not _merge_av(video_tmp, audio_tmp, output_path):
                    # If merge failed, just keep the video file
                    if os.path.exists(video_tmp):
                        os.rename(video_tmp, output_path)
                    else:
                        return {'error': 'FFmpeg merge failed'}
            else:
                # No audio, just rename video
                os.rename(video_tmp, output_path)

        finally:
            # Clean up temp files
            for tmp in [video_tmp, audio_tmp]:
                if os.path.exists(tmp):
                    os.remove(tmp)

    elif durl:
        # Combined format (FLV/MP4) - select highest quality by order field
        # durl list may contain multiple quality levels; 'order' field indicates quality rank
        best_durl = max(durl, key=lambda x: x.get('order', 0))
        combined_url = best_durl.get('url')
        if not combined_url:
            return {'error': 'No video URL found'}

        if progress_callback:
            progress_callback(title, 0, None, None, None)

        if not _download_stream(combined_url, output_path, cookie_str, progress_callback,
                                 safe_title, cancel_event):
            return {'error': 'cancelled' if cancel_event and cancel_event.is_set() else 'Download failed'}

    else:
        return {'error': 'No video data found in page'}

    if not os.path.exists(output_path):
        return {'error': 'Output file not created'}

    filesize = os.path.getsize(output_path)
    if progress_callback:
        progress_callback(title, 100.0, None, None, f'{filesize / 1024 / 1024:.1f} MB')

    return {
        'title': title,
        'filepath': output_path,
        'filesize': filesize,
        'author': author,
        'thumbnail': (metadata or {}).get('pic'),
    }
