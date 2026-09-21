"""Douyin video downloader - Android compatible (a_bogus signed API call)."""
from __future__ import annotations
import json
import logging
import os
import random
import re
import time
import urllib.request
from urllib.error import HTTPError, URLError

from abogus import ABogus, BrowserFingerprintGenerator

from ..utils import _fetch_douyin_ttwid, _resolve_douyin_url

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 2


def _call_douyin_api(aweme_id, ttwid):
    """Call Douyin API with a_bogus signature. Returns parsed JSON or raises."""
    user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'
    params = {
        "device_platform": "webapp", "aid": "6383", "channel": "channel_pc_web",
        "aweme_id": aweme_id, "pc_client_type": "1", "publish_video_strategy_type": "2",
        "pc_libra_divert": "Windows", "version_code": "290100", "version_name": "29.1.0",
        "cookie_enabled": "true", "screen_width": "1920", "screen_height": "1080",
        "browser_language": "zh-CN", "browser_platform": "Win32",
        "browser_name": "Edge", "browser_version": "131.0.0.0",
        "browser_online": "true", "engine_name": "Blink", "engine_version": "131.0.0.0",
        "os_name": "Windows", "os_version": "10",
        "cpu_core_num": "12", "device_memory": "8", "platform": "PC",
        "downlink": "10", "effective_type": "4g", "round_trip_time": "100",
        "msToken": "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789") for _ in range(126)) + "==",
    }

    param_str = "&".join([f"{k}={v}" for k, v in params.items()])
    base_endpoint = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
    browser_fp = BrowserFingerprintGenerator.generate_fingerprint("Edge")
    ab = ABogus(fp=browser_fp, user_agent=user_agent)
    ab_result = ab.generate_abogus(param_str, "")
    ab_value = ab_result[1]
    api_url = f"{base_endpoint}?{param_str}&a_bogus={ab_value}"

    cookie_str = f'ttwid={ttwid}; msToken={params["msToken"]};' if ttwid else f'msToken={params["msToken"]};'
    api_headers = {
        'User-Agent': user_agent, 'Accept': 'application/json',
        'Referer': 'https://www.douyin.com/', 'Cookie': cookie_str,
    }
    api_req = urllib.request.Request(api_url, headers=api_headers)
    api_resp = urllib.request.urlopen(api_req, timeout=30)
    api_data = json.loads(api_resp.read().decode('utf-8'))
    api_resp.close()
    return api_data


def _download_douyin_direct(task, url, download_dir):
    """Download Douyin video using a_bogus signed API call."""
    task['status'] = 'starting'
    task['title'] = '正在解析抖音链接...'

    # Step 1: Resolve short URL
    aweme_id, final_url = _resolve_douyin_url(url)
    if not aweme_id:
        raise Exception(f"Cannot find aweme_id in URL: {final_url}")
    logger.info(f"[Task {task['id']}] aweme_id: {aweme_id}")

    # Step 2: Call API with retry on 403
    task['title'] = '正在获取视频信息...'
    api_data = None
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            ttwid = _fetch_douyin_ttwid()
            api_data = _call_douyin_api(aweme_id, ttwid)
            break
        except HTTPError as e:
            last_error = e
            logger.warning(f"[Task {task['id']}] API call attempt {attempt+1}/{_MAX_RETRIES} failed: HTTP {e.code}")
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY)
        except Exception as e:
            last_error = e
            logger.warning(f"[Task {task['id']}] API call attempt {attempt+1}/{_MAX_RETRIES} error: {e}")
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY)

    if api_data is None:
        raise Exception(f"Douyin API failed after {_MAX_RETRIES} retries: {last_error}")

    # Step 6: Parse response
    status_code = api_data.get('status_code', -1)
    aweme_detail = api_data.get('aweme_detail')
    if not aweme_detail:
        raise Exception(f"Douyin API error: status_code={status_code}")

    title = aweme_detail.get('desc', '') or f'douyin_{aweme_id}'
    safe_title = re.sub(r'[<>\":/\\|?*\n\r\t#]', '_', title)[:80].strip()
    if not safe_title:
        safe_title = f'douyin_{aweme_id}'
    task['title'] = safe_title

    # Log aweme type and available fields for debugging
    aweme_type = aweme_detail.get('aweme_type', 'unknown')
    logger.info(f"[Task {task['id']}] aweme_type={aweme_type}, keys={list(aweme_detail.keys())}")

    # Check if this is an image post (图文) or video
    # Try multiple possible field names for images
    images = None
    for field in ['images', 'image_post_info', 'image_list']:
        val = aweme_detail.get(field)
        if val:
            if isinstance(val, list):
                images = val
            elif isinstance(val, dict):
                images = val.get('images', [])
            if images:
                logger.info(f"[Task {task['id']}] Found images in field '{field}': {len(images)} items")
                break

    # Also check aweme_type - type 68 is typically image post
    if not images and aweme_type in [68, '68']:
        logger.warning(f"[Task {task['id']}] aweme_type={aweme_type} suggests image post but no images field found")
        # Try to extract from video field as fallback
        video = aweme_detail.get('video', {})
        if video:
            logger.info(f"[Task {task['id']}] video keys: {list(video.keys())}")

    if images and isinstance(images, list) and len(images) > 0:
        # Image post (图文) - download all images
        logger.info(f"[Task {task['id']}] Douyin image post with {len(images)} images")
        task['title'] = f'{safe_title} (图文)'

        folder_path = os.path.join(download_dir, safe_title)
        os.makedirs(folder_path, exist_ok=True)

        for i, img in enumerate(images):
            # Extract image URL from various possible structures
            img_url = None
            if isinstance(img, dict):
                # Try different field names
                img_url = (img.get('url') or
                          img.get('download_url') or
                          img.get('display_image', {}).get('url_list', [None])[0] or
                          img.get('original_image', {}).get('url_list', [None])[0])

                # Try url_list structure
                if not img_url:
                    url_list = img.get('url_list', [])
                    if url_list:
                        img_url = url_list[0]

            if not img_url:
                logger.warning(f"[Task {task['id']}] Could not extract URL for image {i+1}")
                continue

            # Determine extension
            ext = '.jpg'
            if '.png' in img_url.lower():
                ext = '.png'
            elif '.webp' in img_url.lower():
                ext = '.webp'

            filename = f'{safe_title}_{i+1:03d}{ext}'
            filepath = os.path.join(folder_path, filename)

            task['status'] = 'downloading'
            task['title'] = f'{safe_title} ({i+1}/{len(images)})'

            dl_req = urllib.request.Request(img_url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
                'Referer': 'https://www.douyin.com/',
            })
            try:
                dl_resp = urllib.request.urlopen(dl_req, timeout=60)
                with open(filepath, 'wb') as f:
                    while True:
                        chunk = dl_resp.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                dl_resp.close()
            except Exception as e:
                logger.warning(f"[Task {task['id']}] Failed to download image {i+1}: {e}")

        task['status'] = 'completed'
        task['progress_pct'] = 100.0
        task['filename'] = folder_path
        task['completed_at'] = time.time()
        logger.info(f"[Task {task['id']}] Douyin images downloaded: {folder_path}")
        return

    # Video post - extract video URL
    video = aweme_detail.get('video', {})
    video_url = None
    bit_rate = video.get('bit_rate', [])
    if bit_rate and isinstance(bit_rate, list):
        sorted_br = sorted(bit_rate, key=lambda x: x.get('bit_rate', 0), reverse=True)
        for br in sorted_br:
            br_urls = br.get('play_addr', {}).get('url_list', [])
            if br_urls:
                video_url = br_urls[0]
                break
    if not video_url:
        url_list = video.get('play_addr', {}).get('url_list', [])
        if url_list:
            video_url = url_list[0]
    if not video_url:
        raise Exception("Cannot find video URL in API response")

    # Step 7: Download the video (with retry on 403)
    task['status'] = 'downloading'
    os.makedirs(download_dir, exist_ok=True)
    filepath = os.path.join(download_dir, f'{safe_title}.mp4')
    if os.path.exists(filepath):
        filepath = os.path.join(download_dir, f'{safe_title}_{int(time.time())}.mp4')

    dl_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0'
    dl_headers = {'User-Agent': dl_ua, 'Referer': 'https://www.douyin.com/'}

    dl_success = False
    for dl_attempt in range(_MAX_RETRIES):
        try:
            dl_req = urllib.request.Request(video_url, headers=dl_headers)
            dl_resp = urllib.request.urlopen(dl_req, timeout=300)
            total_size = int(dl_resp.headers.get('Content-Length', 0))
            downloaded = 0
            start_time = time.time()

            with open(filepath, 'wb') as f:
                while True:
                    chunk = dl_resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        task['progress_pct'] = round(downloaded / total_size * 100, 1)
                        elapsed = time.time() - start_time
                        if elapsed > 0:
                            speed = downloaded / elapsed
                            task['speed'] = f'{speed / 1024 / 1024:.1f} MB/s' if speed > 1024 * 1024 else f'{speed / 1024:.0f} KB/s'
                        remaining = total_size - downloaded
                        if speed > 0:
                            eta = int(remaining / speed)
                            task['eta'] = f'{eta}s' if eta < 60 else f'{eta // 60}m{eta % 60}s'
                        task['filesize'] = f'{total_size / 1024 / 1024:.1f} MB'
            dl_resp.close()
            dl_success = True
            break
        except HTTPError as e:
            logger.warning(f"[Task {task['id']}] Download attempt {dl_attempt+1}/{_MAX_RETRIES} failed: HTTP {e.code}")
            if os.path.exists(filepath):
                os.remove(filepath)
            if dl_attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY)
        except Exception as e:
            logger.warning(f"[Task {task['id']}] Download attempt {dl_attempt+1}/{_MAX_RETRIES} error: {e}")
            if os.path.exists(filepath):
                os.remove(filepath)
            if dl_attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY)

    if not dl_success:
        raise Exception(f"Video download failed after {_MAX_RETRIES} retries")

    task['status'] = 'completed'
    task['progress_pct'] = 100.0
    task['filename'] = filepath
    task['completed_at'] = time.time()
    logger.info(f"[Task {task['id']}] Douyin download completed: {filepath}")
