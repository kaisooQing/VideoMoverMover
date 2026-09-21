"""Xiaohongshu video/image downloader - Android compatible (HTTP requests)."""
from __future__ import annotations
import json
import logging
import os
import re
import time
import urllib.request
from urllib.parse import urlparse, parse_qs, urlencode

logger = logging.getLogger(__name__)


def _download_xiaohongshu_direct(task, url, download_dir):
    """Download Xiaohongshu post (images or video) using HTTP requests."""
    task['status'] = 'starting'
    task['title'] = '正在解析小红书链接...'

    desktop_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0'

    # Step 1: Normalize URL
    logger.info(f"[Task {task['id']}] Original XHS URL: {url}")

    # Resolve short link if needed
    if 'xhslink.' in url:
        req = urllib.request.Request(url, headers={'User-Agent': desktop_ua})
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            url = resp.url
            resp.close()
            logger.info(f"[Task {task['id']}] Resolved short link: {url}")
        except Exception as e:
            logger.warning(f"[Task {task['id']}] Short link resolve failed: {e}")

    # Extract note ID and build proper URL (support multiple URL shapes)
    note_id = None
    match = re.search(r'/(?:explore|discovery/item|note|search_result)/([a-f0-9]+)', url)
    if match:
        note_id = match.group(1)

    if not note_id:
        # Generic 24-char hex id anywhere in the path
        match = re.search(r'/([a-f0-9]{24})(?:[/?]|$)', url)
        if match:
            note_id = match.group(1)

    if not note_id:
        # Fall back to query params (note_id / id)
        _qs = parse_qs(urlparse(url).query)
        for _k in ('note_id', 'id', 'noteId'):
            if _qs.get(_k):
                note_id = _qs[_k][0]
                break

    if not note_id:
        raise Exception("Cannot find note ID in URL")

    # Preserve important query params
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    keep_params = {}
    for key in ['xsec_token', 'xsec_source', 'share_id', 'type']:
        if key in params:
            keep_params[key] = params[key]

    if keep_params:
        query = urlencode(keep_params, doseq=True)
        page_url = f'https://www.xiaohongshu.com/discovery/item/{note_id}?{query}'
    else:
        page_url = f'https://www.xiaohongshu.com/discovery/item/{note_id}?xsec_source=app_share&type=normal'

    logger.info(f"[Task {task['id']}] XHS page URL: {page_url}")

    # Step 2: Fetch page and extract __INITIAL_STATE__
    task['title'] = '正在获取笔记信息...'
    req = urllib.request.Request(page_url, headers={
        'User-Agent': desktop_ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    })

    resp = urllib.request.urlopen(req, timeout=20)
    html = resp.read().decode('utf-8', errors='replace')
    resp.close()

    state_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*</script>', html, re.DOTALL)
    if not state_match:
        raise Exception("No __INITIAL_STATE__ found in page")

    raw = state_match.group(1).replace('undefined', 'null')
    state = json.loads(raw)

    note_map = state.get('note', {}).get('noteDetailMap', {})
    if not note_map:
        raise Exception("noteDetailMap is empty")

    note_key = list(note_map.keys())[0]
    note = note_map[note_key].get('note', {})

    note_type = note.get('type', '')
    title = note.get('title', '') or note.get('desc', '')[:50] or 'untitled'
    author = note.get('user', {}).get('nickname', '')

    safe_title = re.sub(r'[<>\":/\\|?*\n\r\t]', '_', title)[:80].strip()
    if not safe_title:
        safe_title = f'xhs_{note_id}'

    task['title'] = safe_title
    logger.info(f"[Task {task['id']}] XHS note: type={note_type}, title={title[:30]}")

    # Step 3: Extract and download content
    images = note.get('imageList', [])
    video = note.get('video', {})
    video_urls = []

    if video:
        media = video.get('media', {})
        stream = media.get('stream', {})
        for codec_key, streams_list in stream.items():
            if isinstance(streams_list, list):
                for s in streams_list:
                    master = s.get('masterUrl', '')
                    if master:
                        video_urls.append(master)

    os.makedirs(download_dir, exist_ok=True)

    logger.info(f"[Task {task['id']}] XHS note_type={note_type}, images={len(images)}, video_urls={len(video_urls)}")

    if images and not video_urls:
        # Image post (图文) - regardless of note_type
        task['title'] = f'{safe_title} (图文)'
        folder_path = os.path.join(download_dir, safe_title)
        os.makedirs(folder_path, exist_ok=True)

        total = len(images)
        for i, img in enumerate(images):
            img_url = img.get('urlDefault') or img.get('urlPre', '')
            if not img_url:
                continue

            ext = '.jpg'
            if '.png' in img_url.lower():
                ext = '.png'
            elif '.webp' in img_url.lower():
                ext = '.webp'

            filename = f'{safe_title}_{i+1:03d}{ext}'
            filepath = os.path.join(folder_path, filename)

            task['status'] = 'downloading'
            task['title'] = f'{safe_title} ({i+1}/{total})'

            dl_req = urllib.request.Request(img_url, headers={
                'User-Agent': desktop_ua,
                'Referer': 'https://www.xiaohongshu.com/',
            })
            dl_resp = urllib.request.urlopen(dl_req, timeout=60)
            with open(filepath, 'wb') as f:
                while True:
                    chunk = dl_resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
            dl_resp.close()

        task['status'] = 'completed'
        task['progress_pct'] = 100.0
        task['filename'] = folder_path
        task['completed_at'] = time.time()
        logger.info(f"[Task {task['id']}] XHS images downloaded: {folder_path}")

    elif video_urls:
        # Video post
        video_url = video_urls[0]
        filepath = os.path.join(download_dir, f'{safe_title}.mp4')
        if os.path.exists(filepath):
            filepath = os.path.join(download_dir, f'{safe_title}_{int(time.time())}.mp4')

        task['status'] = 'downloading'
        task['title'] = safe_title

        dl_req = urllib.request.Request(video_url, headers={
            'User-Agent': desktop_ua,
            'Referer': 'https://www.xiaohongshu.com/',
        })
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
        dl_resp.close()

        task['status'] = 'completed'
        task['progress_pct'] = 100.0
        task['filename'] = filepath
        task['completed_at'] = time.time()
        logger.info(f"[Task {task['id']}] XHS video downloaded: {filepath}")

    else:
        raise Exception("No downloadable content found in note")
