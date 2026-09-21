"""WeChat Channels (微信视频号) download module.

Uses a third-party online parser API to resolve video share links
to direct video URLs, then downloads the video file.
"""
import json
import logging
import os
import re
import socket
import time
import urllib.request
from urllib.error import URLError

logger = logging.getLogger(__name__)

# 第三方视频号解析 API 地址列表（按优先级排序）
# 主地址：原作者提供的 Cloudflare Workers 服务
# 备用地址：用户可以部署自己的 Workers 实例并添加到这里
# 如果主地址在国内网络下不可用，建议用户自建 Workers 服务
_API_BASES = [
    'https://sph.litao.workers.dev',
    # 'https://your-custom-domain.workers.dev',  # 自建备用地址
]

_MAX_RETRIES = 2
_RETRY_DELAY = 2

_MOBILE_UA = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 '
    'Mobile/15E148 Safari/604.1'
)


def is_wechat_channels_url(url):
    """Check if the URL is a WeChat Channels (视频号) share link."""
    patterns = [
        r'weixin\.qq\.com/sph/',
        r'channels\.weixin\.qq\.com',
        r'findermp\.video\.qq\.com',
    ]
    return any(re.search(p, url, re.IGNORECASE) for p in patterns)


def fetch_wechat_channels_info(url):
    """
    Fetch video metadata via the online parser API.

    Returns dict with: title, author, cover_url, video_urls, best_url
    """
    logger.info(f'Fetching WeChat Channels info: {url}')

    body = json.dumps({'url': url}).encode('utf-8')
    req = urllib.request.Request(
        _API_FETCH,
        data=body,
        headers={
            'User-Agent': _MOBILE_UA,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method='POST',
    )

    try:
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read().decode('utf-8'))
        resp.close()
    except Exception as e:
        logger.warning(f'API request failed: {e}')
        return {'error': f'Failed to resolve video: {e}'}

    if data.get('errCode') != 0:
        err_msg = data.get('errMsg', 'Unknown error')
        return {'error': f'API error: {err_msg}'}

    feed_data = data.get('data', {})
    feed_info = feed_data.get('feedInfo', {})
    author_info = feed_data.get('authorInfo', {})

    if not feed_info:
        return {'error': 'No video info returned from API'}

    # Build video URL list (best quality first)
    video_urls = []
    best_url = None

    # Prefer H264 (best compatibility), fallback to H265, then plain videoUrl
    for key in ('h264VideoInfo', 'h265VideoInfo'):
        info = feed_info.get(key)
        if info and isinstance(info, dict):
            vurl = info.get('videoUrl')
            if vurl:
                video_urls.append(vurl)
                if not best_url:
                    best_url = vurl
                    logger.info(f'Using {key} video URL')

    plain_url = feed_info.get('videoUrl')
    if plain_url and plain_url not in video_urls:
        video_urls.append(plain_url)
        if not best_url:
            best_url = plain_url

    if not video_urls:
        return {'error': 'No video URL found in API response'}

    title = feed_info.get('description', '')
    author = author_info.get('nickname', '')
    cover = feed_info.get('coverUrl', '')

    return {
        'title': title or 'wechat_channels_video',
        'author': author,
        'cover_url': cover,
        'video_urls': video_urls,
        'best_url': best_url,
    }


def _download_file(url, filepath, progress_callback=None,
                   label='', cancel_event=None):
    """Download a file with progress reporting and automatic retry."""
    _VALID_TYPES = (
        'video/', 'image/', 'application/octet-stream', 'application/mp4',
        'binary/octet-stream',
    )

    for attempt in range(_MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': _MOBILE_UA,
                'Referer': 'https://weixin.qq.com/',
            })
            resp = urllib.request.urlopen(req, timeout=60)

            content_type = resp.headers.get('Content-Type', '').lower().split(';')[0].strip()
            if content_type and not any(content_type.startswith(v) for v in _VALID_TYPES):
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
                        progress_callback(label, pct, speed_str, None, total_str)

            resp.close()

            actual_size = os.path.getsize(filepath)
            if total_size > 0 and abs(actual_size - total_size) > 1024:
                logger.warning(f'File size mismatch: expected {total_size}, got {actual_size}')
                if attempt < _MAX_RETRIES:
                    os.remove(filepath)
                    time.sleep(_RETRY_DELAY)
                    continue
                return False

            if filepath.endswith('.mp4'):
                with open(filepath, 'rb') as f:
                    header = f.read(32)
                if len(header) >= 8:
                    box_type = header[4:8]
                    if box_type not in (b'ftyp', b'moov', b'mdat'):
                        logger.warning(f'Invalid MP4 header: {header[:16].hex()}')
                        if attempt < _MAX_RETRIES:
                            os.remove(filepath)
                            time.sleep(_RETRY_DELAY)
                            continue
                        return False

            return True

        except (socket.timeout, TimeoutError, URLError, OSError, Exception) as e:
            error_str = str(e).lower()
            is_timeout = 'timed out' in error_str or isinstance(e, (socket.timeout, TimeoutError))
            category = 'timeout' if is_timeout else 'error'
            logger.warning(f'Download {category} (attempt {attempt + 1}/{_MAX_RETRIES + 1}): {e}')
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


def download_wechat_channels_sync(
    url,
    download_dir,
    progress_callback=None,
    cancel_event=None,
):
    """
    Download a WeChat Channels video synchronously.

    Returns dict with: title, filepath, filesize, author, thumbnail
    """
    info = fetch_wechat_channels_info(url)
    if 'error' in info:
        return info

    title = info.get('title', 'untitled') or 'untitled'
    safe_title = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', title)[:80].strip()
    if not safe_title:
        safe_title = 'wechat_channels_video'

    os.makedirs(download_dir, exist_ok=True)
    filepath = os.path.join(download_dir, f'{safe_title}.mp4')

    if os.path.exists(filepath):
        base, ext = os.path.splitext(filepath)
        filepath = f'{base}_{int(time.time())}{ext}'

    video_urls = info.get('video_urls', [])
    best_url = info.get('best_url')
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

        if _download_file(video_url, filepath, progress_callback, title, cancel_event):
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
