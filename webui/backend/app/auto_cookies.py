"""Auto-fetch cookies from video platforms using Playwright + Edge."""
from __future__ import annotations
import asyncio
import http.cookiejar
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

import sys as _sys
if getattr(_sys, 'frozen', False):
    COOKIE_DIR = os.path.join(os.path.dirname(_sys.executable), 'cookies')
else:
    COOKIE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'cookies')
os.makedirs(COOKIE_DIR, exist_ok=True)

# Platform cookie domains
PLATFORM_DOMAINS = {
    'douyin': ['.douyin.com', 'www.douyin.com'],
    'tiktok': ['.tiktok.com', 'www.tiktok.com'],
    'bilibili': ['.bilibili.com', 'www.bilibili.com'],
    'weibo': ['.weibo.com', 'www.weibo.com'],
}

# URLs to visit for cookie generation
PLATFORM_URLS = {
    'douyin': 'https://www.douyin.com/',
    'tiktok': 'https://www.tiktok.com/',
    'bilibili': 'https://www.bilibili.com/',
    'weibo': 'https://www.weibo.com/',
}


def detect_platform(url: str) -> str | None:
    """Detect which platform a URL belongs to."""
    url_lower = url.lower()
    for platform, domains in PLATFORM_DOMAINS.items():
        for domain in domains:
            if domain.lstrip('.') in url_lower:
                return platform
    # Also check short URLs
    if 'v.douyin.com' in url_lower or 'douyin.com' in url_lower:
        return 'douyin'
    if 'vm.tiktok.com' in url_lower or 'vt.tiktok.com' in url_lower:
        return 'tiktok'
    return None


def cookies_to_netscape(cookies: list[dict], domain_filter: list[str] | None = None) -> str:
    """Convert Playwright cookies to Netscape cookies.txt format."""
    lines = ['# Netscape HTTP Cookie File', '# https://curl.se/docs/http-cookies.html', '']
    for c in cookies:
        domain = c.get('domain', '')
        if domain_filter and not any(domain.endswith(d) for d in domain_filter):
            continue
        # Netscape format: domain  flag  path  secure  expiration  name  value
        flag = 'TRUE' if domain.startswith('.') else 'FALSE'
        path = c.get('path', '/')
        secure = 'TRUE' if c.get('secure', False) else 'FALSE'
        expires = str(int(c.get('expires', -1))) if c.get('expires', -1) > 0 else '0'
        name = c.get('name', '')
        value = c.get('value', '')
        lines.append(f'{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}')
    return '\n'.join(lines)


async def fetch_cookies_for_url(url: str) -> dict:
    """
    Use Playwright + Edge to automatically fetch cookies from a video platform.
    Returns dict with cookie file path and metadata.
    """
    platform = detect_platform(url)
    if not platform:
        return {'error': f'Unknown platform for URL: {url}'}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {'error': 'Playwright not installed. Run: pip install playwright'}

    visit_url = PLATFORM_URLS.get(platform, url)
    domains = PLATFORM_DOMAINS.get(platform, [])

    logger.info(f'Auto-fetching cookies for {platform} by visiting {visit_url}')

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                channel='msedge',
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--window-position=-10000,-10000',
                    '--window-size=1,1',
                ],
            )
        except Exception as e:
            # Fallback: try without channel (use bundled chromium if available)
            try:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--window-position=-10000,-10000',
                        '--window-size=1,1',
                    ],
                )
            except Exception as e2:
                return {'error': f'Cannot launch browser: {e2}. Install Edge or run: python -m playwright install chromium'}

        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0',
            locale='zh-CN',
        )

        page = await context.new_page()

        try:
            # Navigate to the platform's homepage to get cookies
            await page.goto(visit_url, wait_until='domcontentloaded', timeout=30000)

            # Wait a bit for JS to set cookies
            await asyncio.sleep(3)

            # Get all cookies
            cookies = await context.cookies()

            logger.info(f'Got {len(cookies)} cookies from {platform}')
            for c in cookies:
                logger.debug(f'  {c["name"]} = {c["value"][:30]}... (domain: {c.get("domain", "?")})')

            # Check for critical cookies
            cookie_names = [c['name'] for c in cookies]
            if platform == 'douyin':
                has_s_v = 's_v_web_id' in cookie_names
                has_ttwid = 'ttwid' in cookie_names
                logger.info(f'Douyin critical cookies: s_v_web_id={has_s_v}, ttwid={has_ttwid}')

                if not has_s_v:
                    # Try visiting a video page to trigger cookie generation
                    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(3)
                    cookies = await context.cookies()
                    cookie_names = [c['name'] for c in cookies]
                    logger.info(f'After video page visit: {len(cookies)} cookies, s_v_web_id={("s_v_web_id" in cookie_names)}')

            # Save cookies to file
            cookie_content = cookies_to_netscape(cookies, domain_filter=domains)
            timestamp = int(time.time())
            filename = f'{platform}_auto_{timestamp}.txt'
            filepath = os.path.join(COOKIE_DIR, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(cookie_content)

            logger.info(f'Cookies saved to {filepath}')

            return {
                'path': filepath,
                'filename': filename,
                'platform': platform,
                'cookie_count': len(cookies),
                'cookie_names': cookie_names,
                'message': f'Auto-fetched {len(cookies)} cookies from {platform}',
            }

        finally:
            await context.close()
            await browser.close()


# Run async function from sync code
def fetch_cookies_sync(url: str) -> dict:
    """Synchronous wrapper for fetch_cookies_for_url."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, fetch_cookies_for_url(url))
                return future.result(timeout=60)
        else:
            return loop.run_until_complete(fetch_cookies_for_url(url))
    except RuntimeError:
        return asyncio.run(fetch_cookies_for_url(url))
