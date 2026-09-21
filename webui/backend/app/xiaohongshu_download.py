"""Xiaohongshu (小红书) download module.

Handles both image posts (图文) and video posts.
Uses direct HTTP request with proper headers to extract data from __INITIAL_STATE__.
"""
from __future__ import annotations
import json
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

_DESKTOP_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0'
)


def is_xiaohongshu_url(url: str) -> bool:
    """Check if the URL is a Xiaohongshu URL."""
    return bool(re.search(r'xiaohongshu\.com|xhslink\.(?:com|cn)', url, re.IGNORECASE))


def _normalize_url(url: str) -> str:
    """Normalize XHS URL to the discovery/item format that works with __INITIAL_STATE__."""
    # Extract note ID from various URL formats
    # Formats:
    #   https://www.xiaohongshu.com/explore/6a3be2cb...
    #   https://www.xiaohongshu.com/discovery/item/6a3be2cb...
    #   https://xhslink.com/...  (short link)

    if 'xhslink.' in url:
        # Resolve short link
        req = urllib.request.Request(url, headers={'User-Agent': _DESKTOP_UA})
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            url = resp.url
            resp.close()
        except Exception:
            pass

    # Extract note ID
    match = re.search(r'/(?:explore|discovery/item)/([a-f0-9]+)', url)
    if not match:
        return url

    note_id = match.group(1)

    # Preserve important query params (xsec_token etc.)
    from urllib.parse import urlparse, parse_qs, urlencode
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    # Keep essential params
    keep_params = {}
    for key in ['xsec_token', 'xsec_source', 'share_id', 'app_platform',
                'ignoreEngage', 'app_version', 'share_from_user_hidden',
                'type', 'author_share', 'xhsshare', 'shareRedId',
                'apptime', 'share_channel']:
        if key in params:
            keep_params[key] = params[key]

    if keep_params:
        query = urlencode(keep_params, doseq=True)
        return f'https://www.xiaohongshu.com/discovery/item/{note_id}?{query}'
    else:
        # Minimal params - still need to pass something to avoid redirect
        return f'https://www.xiaohongshu.com/discovery/item/{note_id}?xsec_source=app_share&type=normal'


def _fetch_note_data(url: str) -> dict:
    """Fetch note data from XHS page via __INITIAL_STATE__."""
    req = urllib.request.Request(url, headers={
        'User-Agent': _DESKTOP_UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    })

    resp = urllib.request.urlopen(req, timeout=15)
    html = resp.read().decode('utf-8', errors='replace')
    resp.close()

    match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*</script>', html, re.DOTALL)
    if not match:
        return {'error': 'No __INITIAL_STATE__ found in page'}

    raw = match.group(1).replace('undefined', 'null')
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as e:
        return {'error': f'JSON parse error: {e}'}

    note_map = state.get('note', {}).get('noteDetailMap', {})
    if not note_map:
        return {'error': 'noteDetailMap is empty - note may require login or xsec_token'}

    # Get the first (usually only) note
    note_id = list(note_map.keys())[0]
    note = note_map[note_id].get('note', {})

    if not note:
        return {'error': 'Note data is empty'}

    note_type = note.get('type', '')
    title = note.get('title', '') or ''
    desc = note.get('desc', '') or ''
    user = note.get('user', {})
    nickname = user.get('nickname', '')
    user_id = user.get('userId', '')

    result = {
        'note_id': note_id,
        'type': note_type,
        'title': title,
        'desc': desc,
        'author': nickname,
        'user_id': user_id,
    }

    # Extract images
    image_list = note.get('imageList', [])
    images = []
    for img in image_list:
        img_data = {
            'url_default': img.get('urlDefault', ''),
            'url_pre': img.get('urlPre', ''),
            'width': img.get('width'),
            'height': img.get('height'),
        }
        # Try to get highest quality from infoList
        info_list = img.get('infoList', [])
        best_url = img_data['url_default']
        for info in info_list:
            if info.get('imageScene') == 'WB_DFT' and info.get('url'):
                best_url = info['url']
                break
        img_data['url'] = best_url
        images.append(img_data)
    result['images'] = images

    # Extract video - with best quality selection
    video = note.get('video', {})
    if video:
        media = video.get('media', {})
        stream = media.get('stream', {})

        # Extract video cover for thumbnail
        video_cover = (
            video.get('cover', {}).get('url', '')
            or video.get('originVideoCover', '')
            or (images[0].get('url_default') if images else '')
        )
        result['video_cover'] = video_cover

        # Build a quality-ranked list of video URLs
        # Strategy: prefer HD quality, prefer h265 codec (better quality than h264)
        video_urls_by_quality = []

        # Preferred codec order (h265 > av1 > h264)
        codec_priority = {'h265': 0, 'av1': 1, 'h264': 2}

        for codec_key, streams_list in stream.items():
            if not isinstance(streams_list, list):
                continue
            codec_rank = codec_priority.get(codec_key, 99)
            for s in streams_list:
                master = s.get('masterUrl', '')
                quality_type = s.get('qualityType', '')
                is_hd = quality_type.upper() in ('HD', '2K', '4K') if quality_type else False
                if master:
                    video_urls_by_quality.append({
                        'url': master,
                        'codec': codec_key,
                        'codec_rank': codec_rank,
                        'is_hd': is_hd,
                        'quality_type': quality_type,
                    })
                # Also add backup URLs with same quality info
                for backup in s.get('backupUrls', []):
                    if backup:
                        video_urls_by_quality.append({
                            'url': backup,
                            'codec': codec_key,
                            'codec_rank': codec_rank,
                            'is_hd': is_hd,
                            'quality_type': quality_type,
                        })

        # Sort: HD first, then by codec quality (h265 > av1 > h264)
        video_urls_by_quality.sort(key=lambda x: (not x['is_hd'], x['codec_rank']))

        # Log quality selection
        if video_urls_by_quality:
            best = video_urls_by_quality[0]
            logger.info(f'XHS best video: codec={best["codec"]}, quality={best["quality_type"]}, hd={best["is_hd"]}')

        # Flatten to just URLs for backward compatibility
        video_urls = [v['url'] for v in video_urls_by_quality]
        result['video_urls'] = video_urls
    else:
        result['video_urls'] = []

    return result


_MAX_RETRIES = 2
_RETRY_DELAY = 2


def _download_file(url: str, filepath: str, progress_callback: Optional[Callable] = None,
                   label: str = '', cancel_event: Optional[object] = None) -> bool:
    """Download a file with progress reporting and automatic retry on timeout."""
    req = urllib.request.Request(url, headers={
        'User-Agent': _DESKTOP_UA,
        'Referer': 'https://www.xiaohongshu.com/',
    })

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
                        progress_callback(label, pct, speed_str, None, total_str)

            resp.close()
            return True

        except (socket.timeout, TimeoutError, URLError, OSError) as e:
            if 'timed out' in str(e).lower() or isinstance(e, (socket.timeout, TimeoutError)):
                logger.warning(f'Download timed out (attempt {attempt + 1}/{_MAX_RETRIES + 1}): {e}')
                if attempt < _MAX_RETRIES:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    time.sleep(_RETRY_DELAY)
                    continue
            logger.error(f'Download failed: {e}')
            return False

    return False


def download_xiaohongshu_sync(
    url: str,
    download_dir: str,
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[object] = None,
) -> dict:
    """
    Download a Xiaohongshu post (images or video).

    Returns dict with: title, filepath, filesize, author, thumbnail, type
    """
    # Normalize URL
    url = _normalize_url(url)
    logger.info(f'Normalized URL: {url}')

    if progress_callback:
        progress_callback('正在获取笔记信息...', 0, None, None, None)

    # Fetch note data
    try:
        data = _fetch_note_data(url)
    except Exception as e:
        return {'error': f'Failed to fetch note data: {e}'}

    if 'error' in data:
        return data

    note_type = data.get('type', '')
    title = data.get('title', '') or data.get('desc', '')[:50] or 'untitled'
    author = data.get('author', '')
    safe_title = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', title)[:80].strip()
    if not safe_title:
        safe_title = f'xhs_{data.get("note_id", "post")}'

    os.makedirs(download_dir, exist_ok=True)

    images = data.get('images', [])
    video_urls = data.get('video_urls', [])

    if note_type == 'normal' and images and not video_urls:
        # Image post (图文)
        return _download_images(data, images, download_dir, safe_title,
                                progress_callback, cancel_event)
    elif video_urls:
        # Video post
        return _download_video(data, video_urls, download_dir, safe_title,
                               progress_callback, cancel_event)
    elif images:
        # Fallback: download images even if type is not 'normal'
        return _download_images(data, images, download_dir, safe_title,
                                progress_callback, cancel_event)
    else:
        return {'error': 'No downloadable content found in note'}


def _download_images(data, images, download_dir, safe_title,
                     progress_callback, cancel_event):
    """Download all images from an image post to a subfolder."""
    # Create subfolder for images
    folder_path = os.path.join(download_dir, safe_title)
    os.makedirs(folder_path, exist_ok=True)

    total = len(images)
    total_size = 0

    for i, img in enumerate(images):
        if cancel_event and cancel_event.is_set():
            return {'error': 'cancelled'}

        img_url = img.get('url') or img.get('url_default') or img.get('url_pre')
        if not img_url:
            continue

        # Determine extension
        ext = '.jpg'
        if '.png' in img_url.lower():
            ext = '.png'
        elif '.webp' in img_url.lower():
            ext = '.webp'

        filename = f'{safe_title}_{i + 1:03d}{ext}'
        filepath = os.path.join(folder_path, filename)

        label = f'{safe_title} ({i + 1}/{total})'
        if progress_callback:
            progress_callback(label, 0, None, None, None)

        if _download_file(img_url, filepath, progress_callback, label, cancel_event):
            total_size += os.path.getsize(filepath)
        else:
            if cancel_event and cancel_event.is_set():
                return {'error': 'cancelled'}

    if progress_callback:
        progress_callback(safe_title, 100.0, None, None, f'{total_size / 1024 / 1024:.1f} MB')

    return {
        'title': data.get('title', ''),
        'filepath': folder_path,
        'filesize': total_size,
        'author': data.get('author', ''),
        'thumbnail': images[0].get('url_default') if images else None,
        'type': 'images',
        'image_count': total,
    }


def _download_video(data, video_urls, download_dir, safe_title,
                    progress_callback, cancel_event):
    """Download video from a video post."""
    filepath = os.path.join(download_dir, f'{safe_title}.mp4')

    # Avoid overwriting
    if os.path.exists(filepath):
        base, ext = os.path.splitext(filepath)
        filepath = f'{base}_{int(time.time())}{ext}'

    if progress_callback:
        progress_callback(data.get('title', safe_title), 0, None, None, None)

    # Try each video URL until one works
    for url in video_urls:
        if _download_file(url, filepath, progress_callback, safe_title, cancel_event):
            filesize = os.path.getsize(filepath)
            if progress_callback:
                progress_callback(data.get('title', safe_title), 100.0, None, None,
                                  f'{filesize / 1024 / 1024:.1f} MB')
            return {
                'title': data.get('title', ''),
                'filepath': filepath,
                'filesize': filesize,
                'author': data.get('author', ''),
                'thumbnail': data.get('video_cover'),
            }

    return {'error': 'All video URLs failed'}
