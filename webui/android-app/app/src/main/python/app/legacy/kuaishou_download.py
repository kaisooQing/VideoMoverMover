"""Kuaishou (快手) download module.

Supports both video posts and photo/image posts (图文).
Uses mobile User-Agent to bypass captcha and extract data directly from HTML.
Android version - no FFmpeg dependency.
"""
from __future__ import annotations
import json
import logging
import os
import re
import socket
import time
import urllib.request
from typing import Callable, Optional
from urllib.error import URLError

logger = logging.getLogger(__name__)

_MOBILE_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 '
    'Mobile/15E148 Safari/604.1'
)

_DESKTOP_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0'
)

_REFERER = 'https://www.kuaishou.com/'


def is_kuaishou_url(url: str) -> bool:
    """Check if the URL is a Kuaishou URL."""
    return bool(re.search(r'kuaishou\.com|kwai\.com|chenzhongtech\.com', url, re.IGNORECASE))


def _resolve_short_url(url: str) -> str:
    """Resolve a Kuaishou short URL to its full form."""
    req = urllib.request.Request(url, headers={
        'User-Agent': _MOBILE_UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        final_url = resp.url
        resp.close()
        return final_url
    except Exception as e:
        logger.warning(f'Short URL resolve failed: {e}')
        return url


def _fetch_page_html(url: str) -> str:
    """Fetch page HTML with mobile UA."""
    req = urllib.request.Request(url, headers={
        'User-Agent': _MOBILE_UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    })
    resp = urllib.request.urlopen(req, timeout=20)
    html = resp.read().decode('utf-8', errors='replace')
    resp.close()
    return html


def _find_content_entry(state: dict) -> Optional[dict]:
    """Find the content entry in INIT_STATE (keys are Caesar-shifted).

    Returns entries that have a 'photo' field (all share pages have this).
    """
    for v in state.values():
        if isinstance(v, dict) and 'photo' in v:
            return v
    return None


def _build_image_urls(atlas: dict) -> list:
    """Build full image URLs from atlas data."""
    image_list = atlas.get('list', [])
    cdn_list = atlas.get('cdn', atlas.get('cdnList', []))
    if not cdn_list:
        return []

    # Use first CDN domain
    cdn = cdn_list[0] if isinstance(cdn_list[0], str) else cdn_list[0].get('cdn', '')

    urls = []
    for rel_path in image_list:
        if rel_path.startswith('http'):
            urls.append(rel_path)
        else:
            protocol = 'https://'
            urls.append(f'{protocol}{cdn}{rel_path}')
    return urls


def fetch_kuaishou_info(url: str) -> dict:
    """
    Fetch metadata from Kuaishou page. Supports both video and photo (图文) posts.

    Returns dict with: content_id, title, author, cover_url, duration,
                       type ('video' or 'images'),
                       video_urls (for video), image_urls (for images)
    """
    if 'v.kuaishou.com' in url or 'short-video' not in url:
        url = _resolve_short_url(url)

    logger.info(f'Fetching Kuaishou page: {url}')

    html = _fetch_page_html(url)

    if not html:
        return {'error': 'Empty response from Kuaishou'}

    # Extract video/photo ID from URL
    id_match = re.search(r'(?:short-video|photo)/([a-zA-Z0-9_]+)', url)
    content_id = id_match.group(1) if id_match else 'unknown'

    # ---- Try INIT_STATE (mobile share page: videos + photos) ----
    init_match = re.search(r'window\.INIT_STATE\s*=\s*(\{.+?\})\s*</script>', html, re.DOTALL)
    if init_match:
        try:
            raw = init_match.group(1).replace('undefined', 'null')
            state = json.loads(raw)
            return _parse_init_state(state, content_id)
        except Exception as e:
            logger.warning(f'Failed to parse INIT_STATE: {e}')

    # ---- Try __INITIAL_STATE__ (desktop page: videos) ----
    state_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;?\s*</script>', html, re.DOTALL)
    if state_match:
        try:
            raw = state_match.group(1).replace('undefined', 'null')
            state = json.loads(raw)
            return _parse_initial_state(state, content_id, html)
        except Exception as e:
            logger.warning(f'Failed to parse __INITIAL_STATE__: {e}')

    # ---- Fallback: regex extraction from HTML (video only) ----
    return _parse_html_fallback(html, content_id)


def _parse_init_state(state: dict, content_id: str) -> dict:
    """Parse INIT_STATE data from mobile share page."""
    # Find the content entry (has 'photo' field)
    content_entry = _find_content_entry(state)
    if not content_entry:
        return {'error': 'No content found in INIT_STATE'}

    photo = content_entry.get('photo', {})
    atlas = content_entry.get('atlas', {})

    # Image post (图文): has atlas with image list
    if atlas and atlas.get('list'):
        image_urls = _build_image_urls(atlas)
        cover = ''
        cover_urls = photo.get('coverUrls', photo.get('webpCoverUrls', []))
        if cover_urls and isinstance(cover_urls, list):
            cover = cover_urls[0].get('url', '') if isinstance(cover_urls[0], dict) else str(cover_urls[0])

        title = photo.get('caption', '')
        author = photo.get('userName', '')

        return {
            'content_id': content_id,
            'title': title or f'kuaishou_{content_id}',
            'author': author,
            'cover_url': cover,
            'duration': None,
            'type': 'images',
            'image_urls': image_urls,
            'image_count': len(image_urls),
            'video_urls': [],
            'best_url': None,
        }

    # Video post: extract from photo.manifest.adaptationSet[].representation
    video_info = _extract_video_from_photo(photo, content_id)
    if video_info and video_info.get('video_urls'):
        return video_info

    # Fallback: try to find video data directly in state entries
    for v in state.values():
        if isinstance(v, dict):
            if 'representation' in v or 'playUrl' in v:
                return _extract_video_from_entry(v, content_id)

    return {'error': 'No downloadable content found in Kuaishou page'}


def _extract_video_from_photo(photo: dict, content_id: str) -> dict:
    """Extract video URLs from photo.manifest.adaptationSet[].representation.

    Kuaishou mobile share pages store video data inside the photo object's manifest,
    rather than at the top level of INIT_STATE entries.
    """
    video_urls = []
    best_url = None

    manifest = photo.get('manifest', {})
    adapt_sets = manifest.get('adaptationSet', [])

    for adapt_set in adapt_sets:
        representations = adapt_set.get('representation', [])
        # Sort by height and avgBitrate descending to get best quality first
        sorted_reps = sorted(
            representations,
            key=lambda x: (x.get('height', 0), x.get('avgBitrate', 0)),
            reverse=True
        )
        for rep in sorted_reps:
            # Primary URL
            url_val = rep.get('url') or rep.get('src')
            if url_val:
                video_urls.append(url_val)
                if not best_url:
                    best_url = url_val
                    h = rep.get('height', '?')
                    w = rep.get('width', '?')
                    qt = rep.get('qualityType', '?')
                    logger.info(f'Kuaishou best quality: {w}x{h}, type={qt}')

            # Backup URLs (fallback CDN)
            for backup in rep.get('backupUrl', []):
                if backup:
                    video_urls.append(backup)

    if not video_urls:
        return {}

    # Extract metadata from photo object
    cover = ''
    cover_urls = photo.get('coverUrls', photo.get('webpCoverUrls', []))
    if cover_urls and isinstance(cover_urls, list):
        cover = cover_urls[0].get('url', '') if isinstance(cover_urls[0], dict) else str(cover_urls[0])

    title = photo.get('caption', '')
    author = photo.get('userName', '')

    duration = None
    dur = photo.get('duration', 0)
    if isinstance(dur, (int, float)) and dur > 0:
        # Duration is in ms for video posts
        duration = dur / 1000 if dur > 1000 else dur

    return {
        'content_id': content_id,
        'title': title or f'kuaishou_{content_id}',
        'author': author,
        'cover_url': cover,
        'duration': duration,
        'type': 'video',
        'video_urls': video_urls,
        'best_url': best_url,
        'image_urls': [],
        'image_count': 0,
    }


def _extract_video_from_entry(entry: dict, content_id: str) -> dict:
    """Extract video data from an INIT_STATE entry."""
    video_urls = []
    best_url = None

    representations = entry.get('representation', [])
    if representations:
        sorted_reps = sorted(
            representations,
            key=lambda x: (x.get('height', 0), x.get('rate', 0)),
            reverse=True
        )
        for rep in sorted_reps:
            url_val = rep.get('url') or rep.get('src')
            if url_val:
                video_urls.append(url_val)
                if not best_url:
                    best_url = url_val
                    logger.info(f'Kuaishou best quality: {rep.get("width", "?")}x{rep.get("height", "?")}')

    play_url = entry.get('playUrl', '')
    if not best_url and play_url:
        best_url = play_url
        video_urls.append(play_url)

    cover = ''
    for cover_key in ('coverUrl', 'cover', 'poster', 'imageUrl'):
        val = entry.get(cover_key, '')
        if isinstance(val, str) and val:
            cover = val
            break
        elif isinstance(val, dict):
            cover = val.get('url', '') or val.get('urlDefault', '')
            if cover:
                break

    title = entry.get('caption', entry.get('title', ''))
    author = entry.get('userName', entry.get('name', ''))

    duration = None
    dur = entry.get('duration', 0)
    if isinstance(dur, (int, float)) and dur > 0:
        duration = dur / 1000 if dur > 1000 else dur

    if not video_urls:
        return {'error': 'No video URLs found in Kuaishou page'}

    return {
        'content_id': content_id,
        'title': title or f'kuaishou_{content_id}',
        'author': author,
        'cover_url': cover,
        'duration': duration,
        'type': 'video',
        'video_urls': video_urls,
        'best_url': best_url,
        'image_urls': [],
        'image_count': 0,
    }


def _parse_initial_state(state: dict, content_id: str, html: str) -> dict:
    """Parse __INITIAL_STATE__ data from desktop page (video only)."""
    video_data = state.get('video', state.get('main', {}).get('video', {}))
    if video_data:
        return _extract_video_from_entry(video_data, content_id)

    # Fallback to HTML regex
    return _parse_html_fallback(html, content_id)


def _parse_html_fallback(html: str, content_id: str) -> dict:
    """Fallback: extract video URLs via regex from HTML."""
    video_urls = []
    best_url = None

    mp4_urls = re.findall(r'"url":"(https?://[^"]*\.mp4[^"]*)"', html)
    seen = set()
    for u in mp4_urls:
        base = u.split('?')[0]
        if base not in seen:
            seen.add(base)
            video_urls.append(u)

    real_mp4 = [u for u in video_urls if not re.search(r'\.mp4/[a-zA-Z0-9_]', u)]
    if real_mp4:
        video_urls = real_mp4

    cdn_mp4 = [u for u in video_urls if 'kwimgs.com' in u or 'kwaicdn.com' in u]
    if cdn_mp4:
        video_urls = cdn_mp4

    if video_urls:
        best_url = video_urls[0]

    title = ''
    title_match = re.search(r'"caption":"([^"]+)"', html)
    if title_match:
        title = title_match.group(1)

    cover = ''
    cover_match = re.search(r'"coverUrl":"([^"]+)"', html)
    if cover_match:
        cover = cover_match.group(1)

    author = ''
    author_match = re.search(r'"name":"([^"]+)"', html)
    if author_match:
        author = author_match.group(1)

    duration = None
    dur_match = re.search(r'"duration":(\d+)', html)
    if dur_match:
        duration = int(dur_match.group(1)) / 1000

    if not video_urls:
        return {'error': 'No video URLs found in Kuaishou page'}

    return {
        'content_id': content_id,
        'title': title or f'kuaishou_{content_id}',
        'author': author,
        'cover_url': cover,
        'duration': duration,
        'type': 'video',
        'video_urls': video_urls,
        'best_url': best_url,
        'image_urls': [],
        'image_count': 0,
    }


_MAX_RETRIES = 2
_RETRY_DELAY = 2


def _download_file(url: str, filepath: str, progress_callback: Optional[Callable] = None,
                   label: str = '', cancel_event: Optional[object] = None) -> bool:
    """Download a file with progress reporting, Content-Type validation,
    file integrity check, and automatic retry on failure."""
    _VALID_TYPES = (
        'video/', 'image/', 'application/octet-stream', 'application/mp4',
        'binary/octet-stream', 'application/vnd.apple.mpegurl',  # HLS m3u8 playlist
    )

    for attempt in range(_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': _MOBILE_UA,
                'Referer': _REFERER,
            })
            resp = urllib.request.urlopen(req, timeout=60)

            # Validate Content-Type (reject HTML/JSON error pages)
            content_type = resp.headers.get('Content-Type', '').lower().split(';')[0].strip()
            if content_type and not any(content_type.startswith(v) for v in _VALID_TYPES):
                resp.close()
                logger.warning(
                    f'Invalid Content-Type for video (attempt {attempt + 1}): {content_type}'
                )
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
                        progress_callback(label, pct, speed_str, None, total_str)

            resp.close()

            # Validate file integrity: size should roughly match Content-Length
            actual_size = os.path.getsize(filepath)
            if total_size > 0 and abs(actual_size - total_size) > 1024:
                logger.warning(
                    f'File size mismatch: expected {total_size}, got {actual_size}'
                )
                if attempt < _MAX_RETRIES:
                    os.remove(filepath)
                    time.sleep(_RETRY_DELAY)
                    continue
                return False

            # Validate MP4 header for video files
            if filepath.endswith('.mp4'):
                with open(filepath, 'rb') as f:
                    header = f.read(32)
                if len(header) >= 8:
                    box_type = header[4:8]
                    if box_type not in (b'ftyp', b'moov', b'mdat'):
                        logger.warning(
                            f'Invalid MP4 header: {header[:16].hex()}'
                        )
                        if attempt < _MAX_RETRIES:
                            os.remove(filepath)
                            time.sleep(_RETRY_DELAY)
                            continue
                        return False

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


def _is_hls_url(url):
    """Check if the URL points to an HLS stream (m3u8)."""
    return url.endswith('.m3u8') or '.m3u8' in url.split('?')[0]


def _download_hls(url, filepath, progress_callback=None, label='', cancel_event=None):
    """Download an HLS stream using yt-dlp."""
    try:
        import yt_dlp
    except ImportError:
        logger.warning('yt-dlp not available, cannot download HLS stream')
        return False

    try:
        out_dir = os.path.dirname(filepath)
        # Use safe temp name without special chars
        temp_name = f'kuaishou_hls_{int(time.time())}'

        def _progress_hook(d):
            if cancel_event and cancel_event.is_set():
                raise yt_dlp.utils.DownloadError('cancelled')
            if d.get('status') == 'downloading' and progress_callback:
                total = max(d.get('total_bytes', 1), d.get('total_bytes_estimate', 1))
                pct = d.get('downloaded_bytes', 0) / max(total, 1) * 100
                progress_callback(label, round(pct, 1), None, None, None)
            elif d.get('status') == 'finished' and progress_callback:
                progress_callback(label, 100.0, None, None, None)

        ydl_opts = {
            'outtmpl': os.path.join(out_dir, f'{temp_name}.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'progress_hooks': [_progress_hook],
            'socket_timeout': 60,
            'retries': 3,
            'fragment_retries': 3,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded output file
        candidate = None
        for ext in ['.mp4', '.mkv', '.webm', '.ts', '.m4v']:
            c = os.path.join(out_dir, f'{temp_name}{ext}')
            if os.path.exists(c) and os.path.getsize(c) > 1024:
                candidate = c
                break

        if not candidate:
            logger.warning('yt-dlp HLS download finished but no output file found')
            return False

        # Rename to final path
        if candidate != filepath:
            os.replace(candidate, filepath)

        if progress_callback:
            filesize = os.path.getsize(filepath)
            progress_callback(label, 100.0, None, None, f'{filesize / 1024 / 1024:.1f} MB')
        return True

    except yt_dlp.utils.DownloadError as e:
        if 'cancelled' in str(e).lower():
            return False
        logger.warning(f'yt-dlp HLS download failed: {e}')
    except Exception as e:
        logger.warning(f'yt-dlp HLS download exception: {e}')

    return False


def _download_images(info: dict, download_dir: str, safe_title: str,
                     progress_callback: Optional[Callable] = None,
                     cancel_event: Optional[object] = None) -> dict:
    """Download all images from a photo post (图文) to a subfolder."""
    image_urls = info.get('image_urls', [])
    if not image_urls:
        return {'error': 'No image URLs found'}

    # Create subfolder for images
    folder_path = os.path.join(download_dir, safe_title)
    os.makedirs(folder_path, exist_ok=True)

    total = len(image_urls)
    total_size = 0

    for i, img_url in enumerate(image_urls):
        if cancel_event and cancel_event.is_set():
            return {'error': 'cancelled'}

        # Determine extension from URL
        ext = '.jpg'
        url_lower = img_url.lower()
        if '.png' in url_lower:
            ext = '.png'
        elif '.webp' in url_lower:
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
            logger.warning(f'Failed to download image {i + 1}/{total}: {img_url}')

    if progress_callback:
        progress_callback(safe_title, 100.0, None, None, f'{total_size / 1024 / 1024:.1f} MB')

    return {
        'title': info.get('title', ''),
        'filepath': folder_path,
        'filesize': total_size,
        'author': info.get('author', ''),
        'thumbnail': info.get('cover_url'),
        'type': 'images',
        'image_count': total,
    }


def _download_video(info: dict, download_dir: str, safe_title: str,
                    progress_callback: Optional[Callable] = None,
                    cancel_event: Optional[object] = None) -> dict:
    """Download a video post. Tries multiple URLs if the first fails."""
    video_urls = info.get('video_urls', [])
    best_url = info.get('best_url')
    if not video_urls and not best_url:
        return {'error': 'No video URLs found'}

    os.makedirs(download_dir, exist_ok=True)
    filepath = os.path.join(download_dir, f'{safe_title}.mp4')

    # Avoid overwriting
    if os.path.exists(filepath):
        base, ext = os.path.splitext(filepath)
        filepath = f'{base}_{int(time.time())}{ext}'

    title = info.get('title', safe_title)

    # Build ordered list of URLs to try (best first, then fallbacks)
    urls_to_try = []
    if best_url and best_url not in urls_to_try:
        urls_to_try.append(best_url)
    for u in video_urls:
        if u not in urls_to_try:
            urls_to_try.append(u)

    if progress_callback:
        progress_callback(title, 0, None, None, None)

    for video_url in urls_to_try:
        if cancel_event and cancel_event.is_set():
            return {'error': 'cancelled'}

        downloaded = False

        # Handle HLS streams (.m3u8) with yt-dlp
        if _is_hls_url(video_url):
            downloaded = _download_hls(
                video_url, filepath, progress_callback, title, cancel_event
            )
        else:
            downloaded = _download_file(
                video_url, filepath, progress_callback, title, cancel_event
            )

        if downloaded:
            filesize = os.path.getsize(filepath)
            thumbnail = info.get('cover_url', '')

            if progress_callback:
                progress_callback(title, 100.0, None, None, f'{filesize / 1024 / 1024:.1f} MB')

            return {
                'title': info.get('title', ''),
                'filepath': filepath,
                'filesize': filesize,
                'author': info.get('author', ''),
                'thumbnail': thumbnail,
            }

    return {'error': 'All video URLs failed to download'}


def download_kuaishou_sync(
    url: str,
    download_dir: str,
    progress_callback: Optional[Callable] = None,
    cancel_event: Optional[object] = None,
) -> dict:
    """
    Download a Kuaishou post (video or images) synchronously.

    Returns dict with: title, filepath, filesize, author, thumbnail, type
    """
    info = fetch_kuaishou_info(url)
    if 'error' in info:
        return info

    title = info.get('title', 'untitled') or 'untitled'
    safe_title = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', title)[:80].strip()
    if not safe_title:
        safe_title = f'kuaishou_{info.get("content_id", "post")}'

    content_type = info.get('type', 'video')

    if content_type == 'images':
        return _download_images(info, download_dir, safe_title,
                                progress_callback, cancel_event)
    else:
        return _download_video(info, download_dir, safe_title,
                                progress_callback, cancel_event)
