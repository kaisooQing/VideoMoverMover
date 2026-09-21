"""Direct video extraction from Douyin using Playwright + Edge (bypasses yt-dlp's broken extractor)."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import socket
import time
from pathlib import Path
from urllib.error import URLError

logger = logging.getLogger(__name__)


async def extract_douyin_video(url: str, download_dir: str = 'D:/Downloads/yt-dlp') -> dict:
    """
    Extract and download Douyin video directly using Playwright.
    Navigates to the page, intercepts the video data from the page's JS context.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {'error': 'Playwright not installed'}

    # Resolve short URL to full URL
    import urllib.request
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        final_url = resp.url
        resp.close()
    except Exception:
        final_url = url

    logger.info(f'Douyin direct extraction: {url} -> {final_url}')

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                channel='msedge',
                headless=True,
                args=['--disable-blink-features=AutomationControlled'],
            )
        except Exception as e:
            try:
                browser = await p.chromium.launch(headless=True)
            except Exception as e2:
                return {'error': f'Cannot launch browser: {e2}'}

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
            locale='zh-CN',
            viewport={'width': 1920, 'height': 1080},
        )

        page = await context.new_page()

        # Intercept API responses to capture video data
        video_data = {}
        api_responses = []

        async def handle_response(response):
            url = response.url
            if 'aweme/v1/web/aweme/detail' in url or 'aweme/detail' in url:
                try:
                    body = await response.json()
                    if body and 'aweme_detail' in body:
                        video_data['detail'] = body['aweme_detail']
                        logger.info('Captured aweme_detail from API response')
                except Exception:
                    pass

        page.on('response', handle_response)

        try:
            await page.goto(final_url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)  # Wait for API calls

            # If API interception didn't work, try extracting from page context
            if not video_data.get('detail'):
                try:
                    detail = await page.evaluate('''() => {
                        // Try to get video data from page's SSR data or RENDER_DATA
                        const renderData = document.getElementById('RENDER_DATA');
                        if (renderData) {
                            const decoded = decodeURIComponent(renderData.textContent);
                            const data = JSON.parse(decoded);
                            // Navigate through the data to find video info
                            for (const key of Object.keys(data)) {
                                const val = data[key];
                                if (val && val.awemeDetail) return val.awemeDetail;
                                if (val && val.aweme && val.aweme.detail) return val.aweme.detail;
                            }
                        }
                        // Try window.__INITIAL_STATE__
                        if (window.__INITIAL_STATE__) {
                            return window.__INITIAL_STATE__.awemeDetail || null;
                        }
                        return null;
                    }''')
                    if detail:
                        video_data['detail'] = detail
                        logger.info('Captured video data from page context')
                except Exception as e:
                    logger.warning(f'Page context extraction failed: {e}')

            # Extract video URL from the detail data
            detail = video_data.get('detail', {})
            if not detail:
                # Last resort: try to find video element directly
                try:
                    video_src = await page.evaluate('''() => {
                        const video = document.querySelector('video');
                        if (video) return video.src || video.currentSrc || null;
                        // Try xg-video container
                        const xgVideo = document.querySelector('xg-video video, .xgplayer video');
                        if (xgVideo) return xgVideo.src || xgVideo.currentSrc || null;
                        return null;
                    }''')
                    if video_src:
                        return {
                            'title': await page.title(),
                            'video_url': video_src,
                            'method': 'video_element',
                        }
                except Exception:
                    pass

                return {'error': 'Could not extract video data from Douyin page'}

            # Parse the video detail data
            title = detail.get('desc', 'untitled')
            video_info = detail.get('video', {})

            # Get best video URL (prefer play_addr for no watermark)
            play_addr = video_info.get('play_addr', {})
            play_urls = play_addr.get('url_list', [])

            bit_rate = video_info.get('bit_rate', [])
            best_url = None
            best_quality = ''

            if bit_rate:
                # Sort by bit_rate descending, pick the best
                sorted_br = sorted(bit_rate, key=lambda x: x.get('bit_rate', 0), reverse=True)
                for br in sorted_br:
                    urls = br.get('play_addr', {}).get('url_list', [])
                    if urls:
                        best_url = urls[0]
                        best_quality = br.get('gear_name', '')
                        break

            if not best_url and play_urls:
                best_url = play_urls[0]

            if not best_url:
                # Try download_addr
                dl_urls = video_info.get('download_addr', {}).get('url_list', [])
                if dl_urls:
                    best_url = dl_urls[0]
                    best_quality = 'watermarked'

            if not best_url:
                return {'error': 'No video URL found in Douyin data'}

            result = {
                'title': title,
                'video_url': best_url,
                'quality': best_quality,
                'duration': video_info.get('duration', 0) / 1000 if video_info.get('duration') else None,
                'thumbnail': video_info.get('cover', {}).get('url_list', [None])[0],
                'author': detail.get('author', {}).get('nickname', ''),
                'method': 'api_intercept' if video_data.get('detail') else 'page_context',
            }

            # Download the video
            if download_dir:
                os.makedirs(download_dir, exist_ok=True)
                safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)[:80]
                ext = 'mp4'
                filepath = os.path.join(download_dir, f'{safe_title}.{ext}')

                logger.info(f'Downloading video to: {filepath}')
                cookies = await context.cookies()
                cookie_header = '; '.join(f'{c["name"]}={c["value"]}' for c in cookies)

                import urllib.request
                req = urllib.request.Request(best_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://www.douyin.com/',
                    'Cookie': cookie_header,
                })

                _MAX_RETRIES = 2
                _RETRY_DELAY = 2

                for attempt in range(_MAX_RETRIES + 1):
                    try:
                        resp = urllib.request.urlopen(req, timeout=60)
                        with open(filepath, 'wb') as f:
                            while True:
                                chunk = resp.read(1024 * 1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                        resp.close()
                        result['filepath'] = filepath
                        result['filesize'] = os.path.getsize(filepath)
                        logger.info(f'Download complete: {filepath} ({result["filesize"]} bytes)')
                        break

                    except (socket.timeout, TimeoutError, URLError, OSError) as e:
                        if 'timed out' in str(e).lower() or isinstance(e, (socket.timeout, TimeoutError)):
                            logger.warning(f'Douyin direct download timed out (attempt {attempt + 1}/{_MAX_RETRIES + 1}): {e}')
                            if attempt < _MAX_RETRIES:
                                if os.path.exists(filepath):
                                    os.remove(filepath)
                                time.sleep(_RETRY_DELAY)
                                continue
                        result['download_error'] = str(e)
                        logger.error(f'Download failed: {e}')
                        break

                    except Exception as e:
                        result['download_error'] = str(e)
                        logger.error(f'Download failed: {e}')
                        break

            return result

        finally:
            await context.close()
            await browser.close()


def extract_douyin_sync(url: str, download_dir: str = 'D:/Downloads/yt-dlp') -> dict:
    """Synchronous wrapper."""
    try:
        return asyncio.run(extract_douyin_video(url, download_dir))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, extract_douyin_video(url, download_dir))
            return future.result(timeout=120)
