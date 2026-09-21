"""Bilibili video downloader - Android compatible (HTTP requests, no Playwright)."""
from __future__ import annotations
import http.cookiejar
import json
import logging
import os
import re
import shutil
import subprocess
import time
import urllib.request

logger = logging.getLogger(__name__)


def _download_bilibili_direct(task, url, download_dir):
    """Download Bilibili video using HTTP requests (no Playwright)."""
    task['status'] = 'starting'
    task['title'] = '正在解析B站链接...'

    desktop_ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0'

    # Step 1: Resolve short URL
    if 'b23.tv' in url:
        req = urllib.request.Request(url, headers={
            'User-Agent': desktop_ua,
            'Referer': 'https://www.bilibili.com/',
        })
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            url = resp.url
            resp.close()
            logger.info(f"[Task {task['id']}] Resolved b23.tv: {url}")
        except Exception as e:
            logger.warning(f"[Task {task['id']}] b23.tv resolve failed: {e}")

    # Extract BV ID (support path, query param, and av-number fallback)
    bvid = None
    m = re.search(r'/(BV[a-zA-Z0-9]+)', url)
    if m:
        bvid = m.group(1)

    if not bvid:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(url).query)
        if qs.get('bvid'):
            bvid = qs['bvid'][0]

    if not bvid:
        # av-number format (/av123 or ?aid=123): convert to bvid via view API
        av_m = re.search(r'/av(\d+)', url) or re.search(r'[?&]aid=(\d+)', url)
        if av_m:
            aid = av_m.group(1)
            try:
                api = f'https://api.bilibili.com/x/web-interface/view?aid={aid}'
                req = urllib.request.Request(api, headers={
                    'User-Agent': desktop_ua,
                    'Referer': 'https://www.bilibili.com/',
                })
                resp = urllib.request.urlopen(req, timeout=15)
                data = json.loads(resp.read().decode('utf-8', errors='replace'))
                resp.close()
                bvid = (data.get('data') or {}).get('bvid')
                logger.info(f"[Task {task['id']}] Converted av{aid} -> {bvid}")
            except Exception as e:
                logger.warning(f"[Task {task['id']}] av->bvid conversion failed: {e}")

    if not bvid:
        raise Exception("Cannot find BV ID in URL")
    page_url = f'https://www.bilibili.com/video/{bvid}/'
    logger.info(f"[Task {task['id']}] Bilibili page URL: {page_url}")

    # Step 2: Fetch page with proper cookie handling
    task['title'] = '正在获取视频信息...'

    # Create cookie jar and opener
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

    # First visit homepage to get cookies
    try:
        req = urllib.request.Request('https://www.bilibili.com/', headers={
            'User-Agent': desktop_ua,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        resp = opener.open(req, timeout=10)
        resp.close()
        logger.info(f"[Task {task['id']}] Got {len(cookie_jar)} cookies from homepage")
    except Exception as e:
        logger.warning(f"[Task {task['id']}] Homepage cookie fetch failed: {e}")

    # Now fetch the video page with cookies
    req = urllib.request.Request(page_url, headers={
        'User-Agent': desktop_ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': 'https://www.bilibili.com/',
    })

    resp = opener.open(req, timeout=20)
    html = resp.read().decode('utf-8', errors='replace')
    resp.close()

    logger.info(f"[Task {task['id']}] Page HTML length: {len(html)}")

    # Extract __playinfo__
    playinfo = None
    pi_match = re.search(r'window\.__playinfo__\s*=\s*(\{.+?\})\s*;?\s*</script>', html, re.DOTALL)
    if pi_match:
        try:
            playinfo = json.loads(pi_match.group(1))
            logger.info(f"[Task {task['id']}] Successfully extracted __playinfo__")
        except Exception as e:
            logger.warning(f"[Task {task['id']}] __playinfo__ JSON parse failed: {e}")

    if not playinfo or not playinfo.get('data'):
        # Try alternative: use Bilibili API to get video info
        logger.warning(f"[Task {task['id']}] __playinfo__ not found, trying API fallback...")

        # Try to get cid from __INITIAL_STATE__
        cid = None
        aid = None
        is_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;?\s*</script>', html, re.DOTALL)
        if is_match:
            try:
                state = json.loads(is_match.group(1).replace('undefined', 'null'))
                vd = state.get('videoData', {})
                if vd:
                    cid = vd.get('cid')
                    aid = vd.get('aid')
                    title = vd.get('title', title) or title
                    logger.info(f"[Task {task['id']}] Got cid={cid}, aid={aid} from __INITIAL_STATE__")
            except:
                pass

        if not cid:
            # Try API to get cid
            api_url = f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
            api_req = urllib.request.Request(api_url, headers={
                'User-Agent': desktop_ua,
                'Referer': 'https://www.bilibili.com/',
            })
            try:
                api_resp = opener.open(api_req, timeout=15)
                api_data = json.loads(api_resp.read().decode('utf-8'))
                api_resp.close()
                if api_data.get('code') == 0:
                    data_obj = api_data.get('data', {})
                    cid = data_obj.get('cid')
                    aid = data_obj.get('aid')
                    title = data_obj.get('title', title) or title
                    logger.info(f"[Task {task['id']}] Got cid={cid}, aid={aid} from API")
            except Exception as e:
                logger.warning(f"[Task {task['id']}] API call failed: {e}")

        if not cid:
            raise Exception("Cannot extract video info from page. B站可能需要浏览器Cookie才能下载。")

        # Now get playurl using API
        play_api_url = f'https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=80&fnval=16'
        play_req = urllib.request.Request(play_api_url, headers={
            'User-Agent': desktop_ua,
            'Referer': f'https://www.bilibili.com/video/{bvid}/',
        })
        try:
            play_resp = opener.open(play_req, timeout=15)
            play_data = json.loads(play_resp.read().decode('utf-8'))
            play_resp.close()
            if play_data.get('code') == 0:
                playinfo = {'data': play_data.get('data', {})}
                logger.info(f"[Task {task['id']}] Got playinfo from API")
        except Exception as e:
            logger.warning(f"[Task {task['id']}] Playurl API failed: {e}")

        if not playinfo or not playinfo.get('data'):
            raise Exception("Cannot extract video stream info. B站可能需要浏览器Cookie才能下载。")

    # Extract metadata
    title = f'bilibili_{bvid}'
    is_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;?\s*</script>', html, re.DOTALL)
    if is_match:
        try:
            state = json.loads(is_match.group(1).replace('undefined', 'null'))
            vd = state.get('videoData', {})
            title = vd.get('title', title) or title
        except:
            pass

    safe_title = re.sub(r'[<>\":/\\|?*\n\r\t]', '_', title)[:80].strip()
    if not safe_title:
        safe_title = f'bilibili_{bvid}'

    task['title'] = safe_title
    logger.info(f"[Task {task['id']}] Bilibili video: {title[:30]}")

    # Step 3: Download video
    data = playinfo['data']
    dash = data.get('dash')
    durl = data.get('durl')

    os.makedirs(download_dir, exist_ok=True)
    filepath = os.path.join(download_dir, f'{safe_title}.mp4')
    if os.path.exists(filepath):
        filepath = os.path.join(download_dir, f'{safe_title}_{int(time.time())}.mp4')

    task['status'] = 'downloading'

    if dash:
        # DASH: separate video + audio
        videos = dash.get('video', [])
        audios = dash.get('audio', [])

        if not videos:
            raise Exception("No video streams found")

        # Select best video
        videos_sorted = sorted(videos, key=lambda x: x.get('bandwidth', 0), reverse=True)
        video_stream = videos_sorted[0]
        video_url = video_stream.get('baseUrl') or video_stream.get('base_url')

        # Download video stream
        task['title'] = f'{safe_title} (视频)'
        video_tmp = filepath + '.video.m4s'

        dl_req = urllib.request.Request(video_url, headers={
            'User-Agent': desktop_ua,
            'Referer': 'https://www.bilibili.com/',
            'Origin': 'https://www.bilibili.com',
        })
        dl_resp = urllib.request.urlopen(dl_req, timeout=300)
        total_size = int(dl_resp.headers.get('Content-Length', 0))
        downloaded = 0
        start_time = time.time()

        with open(video_tmp, 'wb') as f:
            while True:
                chunk = dl_resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    task['progress_pct'] = round(downloaded / total_size * 50, 1)  # 50% for video
        dl_resp.close()

        # Download audio stream if available
        if audios:
            task['title'] = f'{safe_title} (音频)'
            audios_sorted = sorted(audios, key=lambda x: x.get('bandwidth', 0), reverse=True)
            audio_stream = audios_sorted[0]
            audio_url = audio_stream.get('baseUrl') or audio_stream.get('base_url')

            audio_tmp = filepath + '.audio.m4s'
            dl_req = urllib.request.Request(audio_url, headers={
                'User-Agent': desktop_ua,
                'Referer': 'https://www.bilibili.com/',
                'Origin': 'https://www.bilibili.com',
            })
            dl_resp = urllib.request.urlopen(dl_req, timeout=300)
            total_size = int(dl_resp.headers.get('Content-Length', 0))
            downloaded = 0

            with open(audio_tmp, 'wb') as f:
                while True:
                    chunk = dl_resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        task['progress_pct'] = 50 + round(downloaded / total_size * 45, 1)  # 50-95% for audio
            dl_resp.close()

            # Merge video + audio into final MP4
            task['title'] = f'{safe_title} (合并中...)'
            task['progress_pct'] = 95

            merged = False

            # Method 1: Use Android MediaMuxerHelper (Java) — no FFmpeg needed
            try:
                from java import jclass
                MediaMuxerHelper = jclass("com.ytdlp.webui.MediaMuxerHelper")
                merged = MediaMuxerHelper.merge(video_tmp, audio_tmp, filepath)
                if merged:
                    logger.info(f"[Task {task['id']}] MediaMuxer merge success: {filepath}")
            except Exception as e:
                logger.warning(f"[Task {task['id']}] MediaMuxer merge failed: {e}")

            # Method 2: FFmpeg fallback
            if not merged:
                ffmpeg = shutil.which('ffmpeg')
                if not ffmpeg:
                    for p in ['/data/data/com.ytdlp.webui/files/ffmpeg',
                              '/data/local/tmp/ffmpeg']:
                        if os.path.exists(p):
                            ffmpeg = p
                            break

                if ffmpeg:
                    try:
                        cmd = [ffmpeg, '-y', '-i', video_tmp, '-i', audio_tmp, '-c', 'copy', '-movflags', '+faststart', filepath]
                        result = subprocess.run(cmd, capture_output=True, timeout=300)
                        if result.returncode == 0:
                            merged = True
                            logger.info(f"[Task {task['id']}] ffmpeg merge success: {filepath}")
                        else:
                            stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
                            logger.error(f"[Task {task['id']}] ffmpeg merge failed: {stderr}")
                    except Exception as e:
                        logger.error(f"[Task {task['id']}] ffmpeg merge error: {e}")

            if not merged:
                # Last resort: keep video-only (will have no audio)
                if os.path.exists(video_tmp):
                    shutil.move(video_tmp, filepath)
                    logger.warning(f"[Task {task['id']}] Merge failed, kept video-only (no audio): {filepath}")

            # Clean up temp files
            for tmp in [video_tmp, audio_tmp]:
                if os.path.exists(tmp):
                    os.remove(tmp)
        else:
            # No audio, just rename video
            os.rename(video_tmp, filepath)

    elif durl:
        # Combined format
        best_durl = max(durl, key=lambda x: x.get('order', 0))
        video_url = best_durl.get('url')
        if not video_url:
            raise Exception("No video URL found")

        dl_req = urllib.request.Request(video_url, headers={
            'User-Agent': desktop_ua,
            'Referer': 'https://www.bilibili.com/',
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

    else:
        raise Exception("No video data found")

    task['status'] = 'completed'
    task['progress_pct'] = 100.0
    task['filename'] = filepath
    task['completed_at'] = time.time()
    logger.info(f"[Task {task['id']}] Bilibili download completed: {filepath}")
