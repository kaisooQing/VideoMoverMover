"""Kuaishou video downloader - Android compatible (mobile UA HTML parsing).

Supports both video posts and photo/image posts (图文).
Uses mobile User-Agent to bypass captcha and extract data directly from HTML.
Applies faststart post-processing after download: tries ffmpeg if available,
falls back to pure Python moov atom mover for correct mobile playback duration.
"""
from __future__ import annotations
import json
import logging
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import urllib.request
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

_MAX_RETRIES = 2
_RETRY_DELAY = 2


def _resolve_short_url(url):
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


def _fetch_page_html(url):
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


def _caesar_decode(obj, shift=1):
    """Recursively decode Caesar-shifted keys in INIT_STATE.

    Kuaishou obfuscates INIT_STATE keys with a +1 Caesar shift:
    'photo' -> 'qipup', 'mainMvUrls' -> 'njboNwVsmT', etc.
    This decodes all dict keys back to their original form.
    """
    if isinstance(obj, dict):
        decoded = {}
        for k, v in obj.items():
            new_key = _caesar_shift_str(k, -shift) if isinstance(k, str) else k
            decoded[new_key] = _caesar_decode(v, shift)
        return decoded
    elif isinstance(obj, list):
        return [_caesar_decode(item, shift) for item in obj]
    else:
        return obj


def _caesar_shift_str(s, shift):
    """Shift each letter in string by given amount (wraps around alphabet)."""
    result = []
    for c in s:
        if 'a' <= c <= 'z':
            result.append(chr((ord(c) - ord('a') + shift) % 26 + ord('a')))
        elif 'A' <= c <= 'Z':
            result.append(chr((ord(c) - ord('A') + shift) % 26 + ord('A')))
        else:
            result.append(c)
    return ''.join(result)


def _is_caesar_shifted(state):
    """Check if INIT_STATE keys are Caesar-shifted by looking for known patterns."""
    if not isinstance(state, dict):
        return False
    for key in state.keys():
        if not isinstance(key, str):
            continue
        decoded = _caesar_shift_str(key, -1)
        if any(kw in decoded for kw in ('photo', 'video', 'share', 'system', 'user', 'rest')):
            return True
    return False


def _extract_adaptation_from_mobile_html(html, content_id):
    """Extract video data directly from mobile page HTML's adaptationSet.

    The mobile share page (v.m.chenzhongtech.com) contains adaptationSet JSON
    embedded in the page even without INIT_STATE or __APOLLO_STATE__.
    This function finds and parses it directly.
    """
    # Unescape unicode and backslash-escaped quotes
    html_clean = html.replace('\\u002F', '/').replace('\\u002f', '/')
    # Also handle escaped quotes from JS strings
    html_unescaped = html_clean.replace('\\"', '"')

    direct_mp4 = []

    # Strategy 1: Find mainMvUrls in HTML (direct MP4 URLs, always standard MP4)
    # Try both cleaned and unescaped versions
    for text in [html_clean, html_unescaped]:
        main_mv_urls = re.findall(r'"mainMvUrls?"\s*:\s*\[?\{[^}]*"url"\s*:\s*"(https?://[^"]+)"', text)
        for u in main_mv_urls:
            if u not in direct_mp4:
                direct_mp4.append(u)

    # Strategy 2: Find adaptationSet JSON and extract representation URLs
    adapt_urls = []
    adapt_duration = None
    for text in [html_clean, html_unescaped]:
        if adapt_urls:
            break
        adapt_idx = text.find('"adaptationSet"')
        if adapt_idx >= 0:
            depth = 0
            start = adapt_idx
            for i in range(adapt_idx, max(0, adapt_idx - 5000), -1):
                if text[i] == '}':
                    depth += 1
                elif text[i] == '{':
                    if depth == 0:
                        start = i
                        break
                    depth -= 1
            depth = 0
            end = start
            for i in range(start, min(len(text), start + 50000)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            json_str = text[start:end]
            try:
                data = json.loads(json_str)
                dur = data.get('duration')
                if isinstance(dur, (int, float)) and dur > 0:
                    adapt_duration = dur / 1000 if dur > 1000 else dur
                for adapt_set in data.get('adaptationSet', []):
                    for rep in adapt_set.get('representation', []):
                        url_val = rep.get('url') or rep.get('src')
                        if url_val and url_val not in adapt_urls:
                            adapt_urls.append(url_val)
            except Exception:
                pass

    # Strategy 3: Regex for all MP4 URLs with .mp4 extension
    regex_mp4 = []
    for text in [html_clean, html_unescaped]:
        regex_urls = re.findall(r'"url"\s*:\s*"(https?://[^"]*\.mp4[^"]*)"', text)
        for u in regex_urls:
            if not re.search(r'\.mp4/[a-zA-Z0-9_]', u) and u not in regex_mp4:
                regex_mp4.append(u)

    # Strategy 4: Regex for URLs from known Kuaishou CDN domains (no .mp4 ext needed)
    cdn_urls = []
    cdn_pattern = r'"url"\s*:\s*"(https?://[^"]*(?:kwimgs\.com|yximgs\.com|kwaicdn\.com|ndcimgs\.com)[^"]*)"'
    for text in [html_clean, html_unescaped]:
        found = re.findall(cdn_pattern, text)
        for u in found:
            # Skip non-video URLs (images, audio)
            if re.search(r'\.(jpg|jpeg|png|webp|gif|m4a|mp3|aac|wav)(\?|$)', u, re.IGNORECASE):
                continue
            if u not in cdn_urls and u not in direct_mp4:
                cdn_urls.append(u)

    # Combine all URLs
    all_urls = direct_mp4 + cdn_urls + adapt_urls + regex_mp4

    # Sort by preference
    def _url_priority(u):
        if 'kwimgs.com' in u or 'yximgs.com' in u:
            return 0
        if 'photo-video-mz' in u:
            return 1
        if 'vod-rt-remux' in u or 'hls-ts' in u or 'REALTIME_REMUX' in u:
            return 3
        return 2

    all_urls.sort(key=_url_priority)
    seen = set()
    video_urls = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            video_urls.append(u)

    if not video_urls:
        return None

    # Extract metadata
    title = ''
    for text in [html_clean, html_unescaped]:
        title_match = re.search(r'"caption"\s*:\s*"([^"]+)"', text)
        if title_match:
            title = title_match.group(1)
            break

    cover = ''
    for text in [html_clean, html_unescaped]:
        cover_match = re.search(r'"photoUrl"\s*:\s*"(https?://[^"]+)"', text)
        if not cover_match:
            cover_match = re.search(r'"coverUrl"\s*:\s*"(https?://[^"]+)"', text)
        if cover_match:
            cover = cover_match.group(1)
            break

    author = ''
    for text in [html_clean, html_unescaped]:
        author_match = re.search(r'"userName"\s*:\s*"([^"]+)"', text)
        if not author_match:
            author_match = re.search(r'"name"\s*:\s*"([^"]+)"', text)
        if author_match:
            author = author_match.group(1)
            break

    duration = adapt_duration
    if not duration:
        for text in [html_clean, html_unescaped]:
            dur_match = re.search(r'"duration"\s*:\s*(\d+)', text)
            if dur_match:
                d = int(dur_match.group(1))
                duration = d / 1000 if d > 1000 else d
                break

    return {
        'content_id': content_id,
        'title': title or f'kuaishou_{content_id}',
        'author': author,
        'cover_url': cover,
        'duration': duration,
        'type': 'video',
        'video_urls': video_urls,
        'best_url': video_urls[0],
        'image_urls': [],
        'image_count': 0,
    }


def _fetch_desktop_page(short_url, content_id):
    """Fetch page with desktop UA and parse __APOLLO_STATE__ for video data.

    When mobile UA returns empty INIT_STATE, desktop UA resolves the short URL
    to www.kuaishou.com/short-video/{id} which contains __APOLLO_STATE__
    with adaptationSet (direct MP4 URLs) and photoUrl.
    """
    import ssl

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # Resolve short URL with desktop UA (gets redirected to www.kuaishou.com)
    req = urllib.request.Request(short_url, headers={
        'User-Agent': _DESKTOP_UA,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-CN,zh;q=0.9',
    })
    try:
        resp = urllib.request.urlopen(req, timeout=20, context=ctx)
        final_url = resp.url
        html = resp.read().decode('utf-8', errors='replace')
        resp.close()
    except Exception as e:
        logger.warning(f'Desktop page fetch failed: {e}')
        return None

    if not html:
        return None

    logger.info(f'Desktop page: {final_url}, HTML length: {len(html)}')

    # Unescape Unicode sequences (\u002F -> /)
    html_clean = html.replace('\\u002F', '/').replace('\\u002f', '/')

    # Try to find __APOLLO_STATE__ and extract video data
    apollo_match = re.search(r'__APOLLO_STATE__\s*=\s*(\{)', html_clean)
    if apollo_match:
        result = _parse_apollo_state(html_clean, content_id)
        if result and 'error' not in result:
            return result

    # Fallback: search for adaptationSet JSON object directly in HTML
    result = _parse_adaptation_from_html(html_clean, content_id)
    if result and 'error' not in result:
        return result

    # Last resort: regex search for MP4 URLs in unescaped HTML
    return _parse_html_fallback(html_clean, content_id)


def _parse_apollo_state(html_clean, content_id):
    """Parse __APOLLO_STATE__ from desktop page HTML."""
    # Find __APOLLO_STATE__ JSON
    idx = html_clean.find('__APOLLO_STATE__')
    if idx < 0:
        return None

    # Find the start of the JSON object
    json_start = html_clean.find('{', idx)
    if json_start < 0:
        return None

    # Find the end by matching braces
    depth = 0
    json_end = json_start
    for i in range(json_start, min(len(html_clean), json_start + 500000)):
        c = html_clean[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                json_end = i + 1
                break

    json_str = html_clean[json_start:json_end]
    try:
        apollo = json.loads(json_str)
    except Exception as e:
        logger.warning(f'APOLLO_STATE parse failed: {e}')
        return None

    # Search recursively for adaptationSet or photoUrl
    video_urls = []
    best_url = None
    title = ''
    author = ''
    cover = ''
    duration = None

    def _search(obj):
        nonlocal video_urls, best_url, title, author, cover, duration
        if isinstance(obj, dict):
            if 'adaptationSet' in obj:
                for adapt_set in obj.get('adaptationSet', []):
                    for rep in adapt_set.get('representation', []):
                        url_val = rep.get('url') or rep.get('src')
                        if url_val and url_val not in video_urls:
                            video_urls.append(url_val)
                            if not best_url:
                                best_url = url_val
                                h = rep.get('height', '?')
                                logger.info(f'Desktop video: {h}p')
            if 'photoUrl' in obj and obj['photoUrl']:
                url_val = obj['photoUrl']
                if url_val not in video_urls:
                    video_urls.insert(0, url_val)
                    if not best_url:
                        best_url = url_val
            if 'mainMvUrls' in obj:
                for item in obj.get('mainMvUrls', []):
                    if isinstance(item, dict):
                        url_val = item.get('url') or item.get('src')
                    elif isinstance(item, str):
                        url_val = item
                    else:
                        url_val = None
                    if url_val and url_val not in video_urls:
                        video_urls.insert(0, url_val)
                        if not best_url:
                            best_url = url_val
            if 'caption' in obj and obj['caption'] and not title:
                title = obj['caption']
            if 'name' in obj and obj['name'] and not author:
                author = obj['name']
            if 'userName' in obj and obj['userName'] and not author:
                author = obj['userName']
            if 'coverUrl' in obj and obj['coverUrl'] and not cover:
                cover = obj['coverUrl']
            if 'duration' in obj and isinstance(obj['duration'], (int, float)) and not duration:
                dur = obj['duration']
                duration = dur / 1000 if dur > 1000 else dur
            for v in obj.values():
                _search(v)
        elif isinstance(obj, list):
            for item in obj[:20]:
                _search(item)

    _search(apollo)

    if not video_urls:
        return None

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


def _parse_adaptation_from_html(html_clean, content_id):
    """Extract adaptationSet JSON directly from HTML when APOLLO_STATE is too large."""
    adapt_idx = html_clean.find('"adaptationSet"')
    if adapt_idx < 0:
        return None

    # Find enclosing JSON object by searching backwards for '{'
    depth = 0
    start = adapt_idx
    for i in range(adapt_idx, max(0, adapt_idx - 5000), -1):
        if html_clean[i] == '}':
            depth += 1
        elif html_clean[i] == '{':
            if depth == 0:
                start = i
                break
            depth -= 1

    # Find end
    depth = 0
    end = start
    for i in range(start, min(len(html_clean), start + 50000)):
        if html_clean[i] == '{':
            depth += 1
        elif html_clean[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    json_str = html_clean[start:end]
    try:
        data = json.loads(json_str)
    except Exception:
        return None

    video_urls = []
    for adapt_set in data.get('adaptationSet', []):
        for rep in adapt_set.get('representation', []):
            url_val = rep.get('url') or rep.get('src')
            if url_val and url_val not in video_urls:
                video_urls.append(url_val)

    if not video_urls:
        return None

    # Also search for photoUrl nearby
    photo_match = re.search(r'"photoUrl":"(https?://[^"]+)"', html_clean)
    if photo_match:
        photo_url = photo_match.group(1)
        if photo_url not in video_urls:
            video_urls.insert(0, photo_url)

    duration = None
    dur = data.get('duration')
    if isinstance(dur, (int, float)) and dur > 0:
        duration = dur / 1000 if dur > 1000 else dur

    return {
        'content_id': content_id,
        'title': f'kuaishou_{content_id}',
        'author': '',
        'cover_url': '',
        'duration': duration,
        'type': 'video',
        'video_urls': video_urls,
        'best_url': video_urls[0] if video_urls else None,
        'image_urls': [],
        'image_count': 0,
    }


def _find_content_entry(state):
    """Find the content entry in INIT_STATE (keys are Caesar-shifted).

    Returns entries that have a 'photo' field, or fallback to entries
    with video-related fields like 'mainMvUrls', 'manifest', 'adaptationSet'.
    """
    # Primary: look for entry with 'photo' key
    for v in state.values():
        if isinstance(v, dict) and 'photo' in v:
            return v
    # Fallback: look for entry with video-related fields
    for v in state.values():
        if isinstance(v, dict):
            if any(k in v for k in ('mainMvUrls', 'manifest', 'adaptationSet', 'videoId')):
                return v
            photo = v.get('photo', {})
            if isinstance(photo, dict) and any(k in photo for k in ('mainMvUrls', 'manifest', 'videoId')):
                return v
    return None


def _build_image_urls(atlas):
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


def fetch_kuaishou_info(url):
    """
    Fetch metadata from Kuaishou page. Supports both video and photo (图文) posts.

    Returns dict with: video_id, title, author, cover_url, duration,
                       type ('video' or 'images'),
                       video_urls (for video), image_urls (for images)
    """
    original_url = url
    if 'v.kuaishou.com' in url or 'short-video' not in url:
        url = _resolve_short_url(url)

    logger.info(f'Fetching Kuaishou page: {url}')

    html = _fetch_page_html(url)

    if not html:
        return {'error': 'Empty response from Kuaishou'}

    # Extract video/photo ID from URL (path first, then query param fallbacks)
    id_match = re.search(r'(?:short-video|photo)/([a-zA-Z0-9_]+)', url)
    if id_match:
        content_id = id_match.group(1)
    else:
        from urllib.parse import urlparse, parse_qs
        _qs = parse_qs(urlparse(url).query)
        content_id = (_qs.get('photoId') or _qs.get('id') or [None])[0]
        if not content_id:
            _seg = re.search(r'/([a-zA-Z0-9_]{6,})(?:[/?]|$)', url)
            content_id = _seg.group(1) if _seg else 'unknown'

    # ---- Try adaptationSet extraction from mobile page HTML (most reliable) ----
    # Mobile share pages contain adaptationSet JSON and mainMvUrls embedded
    # directly in HTML. This is more reliable than INIT_STATE parsing
    # (which may be Caesar-shifted/obfuscated) and doesn't need desktop UA.
    mobile_result = _extract_adaptation_from_mobile_html(html, content_id)
    if mobile_result and 'error' not in mobile_result:
        logger.info(f'Extracted {len(mobile_result.get("video_urls", []))} video URL(s) from mobile page')
        return mobile_result

    # ---- Try INIT_STATE (mobile share page: videos + photos) ----
    init_match = re.search(r'window\.INIT_STATE\s*=\s*(\{.+?\})\s*</script>', html, re.DOTALL)
    if init_match:
        try:
            raw = init_match.group(1).replace('undefined', 'null')
            state = json.loads(raw)
            if state:
                # Check if keys are Caesar-shifted and decode them
                if _is_caesar_shifted(state):
                    logger.info('INIT_STATE keys are Caesar-shifted, decoding...')
                    state = _caesar_decode(state)
                result = _parse_init_state(state, content_id)
                if 'error' not in result:
                    return result
                logger.info(f'INIT_STATE parsed but no video: {result.get("error")}')
            else:
                logger.info('INIT_STATE is empty')
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f'Failed to parse INIT_STATE: {e}')

    # ---- Try __INITIAL_STATE__ (desktop page: videos) ----
    state_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.+?\})\s*;?\s*</script>', html, re.DOTALL)
    if state_match:
        try:
            raw = state_match.group(1).replace('undefined', 'null')
            state = json.loads(raw)
            return _parse_initial_state(state, content_id, html)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f'Failed to parse __INITIAL_STATE__: {e}')

    # ---- Try desktop UA (mobile UA may return empty INIT_STATE) ----
    if not state_match or 'kuaishou.com' not in str(url):
        desktop_result = _fetch_desktop_page(original_url, content_id)
        if desktop_result and 'error' not in desktop_result:
            return desktop_result

    # ---- Fallback: regex extraction from HTML (video only) ----
    return _parse_html_fallback(html, content_id)


def _parse_init_state(state, content_id):
    """Parse INIT_STATE data from mobile share page."""
    # Find the content entry (has 'photo' field or video-related fields)
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

    # Video post: extract from photo object (mainMvUrls + manifest)
    video_info = _extract_video_from_photo(photo, content_id)
    if video_info and video_info.get('video_urls'):
        return video_info

    # Fallback 1: try content_entry itself (may have mainMvUrls at top level)
    if content_entry.get('mainMvUrls'):
        photo_like = dict(photo)
        photo_like['mainMvUrls'] = content_entry['mainMvUrls']
        video_info = _extract_video_from_photo(photo_like, content_id)
        if video_info and video_info.get('video_urls'):
            return video_info

    # Fallback 2: search all state values for video data
    for v in state.values():
        if isinstance(v, dict):
            if 'representation' in v or 'playUrl' in v or 'mainMvUrls' in v:
                result = _extract_video_from_entry(v, content_id)
                if result and result.get('video_urls'):
                    return result

    return {'error': 'No downloadable content found in Kuaishou page'}


def _extract_main_mv_urls(photo):
    """Extract direct MP4 URLs from photo.mainMvUrls.

    mainMvUrls provides direct MP4 CDN URLs (no HLS), which are preferred
    for mobile downloads to avoid fMP4 format issues.
    """
    urls = []
    main_mv = photo.get('mainMvUrls', [])
    if not main_mv:
        return urls

    for item in main_mv:
        if isinstance(item, str):
            if item:
                urls.append(item)
        elif isinstance(item, dict):
            url_val = item.get('url') or item.get('src')
            if url_val:
                urls.append(url_val)
    return urls


def _extract_video_from_photo(photo, content_id):
    """Extract video URLs from photo.

    Tries mainMvUrls first (direct MP4, best for mobile), then falls back
    to manifest.adaptationSet[].representation (may include HLS).
    """
    video_urls = []
    best_url = None

    # Priority 1: mainMvUrls (direct MP4 URLs, no HLS)
    main_urls = _extract_main_mv_urls(photo)
    if main_urls:
        for u in main_urls:
            if u not in video_urls:
                video_urls.append(u)
        best_url = main_urls[0]
        logger.info(f'Kuaishou: found {len(main_urls)} direct MP4 URL(s) from mainMvUrls')

    # Priority 2: manifest.adaptationSet[].representation
    manifest = photo.get('manifest', {})
    adapt_sets = manifest.get('adaptationSet', [])

    for adapt_set in adapt_sets:
        representations = adapt_set.get('representation', [])
        # Sort: prefer direct MP4 over HLS, then by height descending
        sorted_reps = sorted(
            representations,
            key=lambda x: (not _is_hls_url(x.get('url', '')),
                           x.get('height', 0), x.get('avgBitrate', 0)),
            reverse=True
        )
        for rep in sorted_reps:
            url_val = rep.get('url') or rep.get('src')
            if url_val and url_val not in video_urls:
                video_urls.append(url_val)
                if not best_url:
                    best_url = url_val
                    h = rep.get('height', '?')
                    w = rep.get('width', '?')
                    qt = rep.get('qualityType', '?')
                    logger.info(f'Kuaishou best from manifest: {w}x{h}, type={qt}')

            # Backup URLs (fallback CDN)
            for backup in rep.get('backupUrl', []):
                if backup and backup not in video_urls:
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


def _extract_video_from_entry(entry, content_id):
    """Extract video data from an INIT_STATE entry."""
    video_urls = []
    best_url = None

    # Priority 1: mainMvUrls (direct MP4)
    main_urls = _extract_main_mv_urls(entry)
    if main_urls:
        for u in main_urls:
            if u not in video_urls:
                video_urls.append(u)
        best_url = main_urls[0]
        logger.info(f'Kuaishou: found {len(main_urls)} direct MP4 URL(s) from mainMvUrls')

    # Priority 2: representation list
    representations = entry.get('representation', [])
    if representations:
        sorted_reps = sorted(
            representations,
            key=lambda x: (not _is_hls_url(x.get('url', '')),
                           x.get('height', 0), x.get('rate', 0)),
            reverse=True
        )
        for rep in sorted_reps:
            url_val = rep.get('url') or rep.get('src')
            if url_val and url_val not in video_urls:
                video_urls.append(url_val)
                if not best_url:
                    best_url = url_val
                    logger.info(f'Kuaishou best: {rep.get("width", "?")}x{rep.get("height", "?")}')

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
        # Could be ms or seconds
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


def _parse_initial_state(state, content_id, html):
    """Parse __INITIAL_STATE__ data from desktop page (video only)."""
    video_data = state.get('video', state.get('main', {}).get('video', {}))
    if video_data:
        return _extract_video_from_entry(video_data, content_id)

    # Fallback to HTML regex
    return _parse_html_fallback(html, content_id)


def _parse_html_fallback(html, content_id):
    """Fallback: extract video URLs via regex from HTML."""
    video_urls = []

    # Look for mainMvUrls URLs first (direct MP4, preferred)
    main_mv_matches = re.findall(r'"mainMvUrls?":\s*\[?\{[^}]*"url":"(https?://[^"]+)"', html)
    for u in main_mv_matches:
        if u not in video_urls:
            video_urls.append(u)

    # Look for all MP4 URLs
    mp4_urls = re.findall(r'"url":"(https?://[^"]*\.mp4[^"]*)"', html)
    seen = set()
    for u in mp4_urls:
        base = u.split('?')[0]
        if base not in seen:
            seen.add(base)
            if u not in video_urls:
                video_urls.append(u)

    # Filter out HLS segment URLs (e.g., .mp4/ followed by path = HLS segment)
    real_mp4 = [u for u in video_urls if not re.search(r'\.mp4/[a-zA-Z0-9_]', u)]
    if real_mp4:
        video_urls = real_mp4

    # Sort by priority: standard MP4 first, fMP4 last
    def _url_priority(u):
        if 'kwimgs.com' in u or 'yximgs.com' in u:
            return 0
        if 'photo-video-mz' in u:
            return 1
        if 'vod-rt-remux' in u or 'hls-ts' in u or 'REALTIME_REMUX' in u:
            return 3
        return 2

    video_urls.sort(key=_url_priority)
    best_url = video_urls[0] if video_urls else None

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


def _download_file(url, filepath, task, label=''):
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
                    if task.get('status') == 'cancelled':
                        resp.close()
                        return False

                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        pct = round(downloaded / total_size * 100, 1)
                        elapsed = time.time() - start_time
                        speed = downloaded / elapsed if elapsed > 0 else 0
                        if speed > 1024 * 1024:
                            speed_str = f'{speed / 1024 / 1024:.1f} MB/s'
                        else:
                            speed_str = f'{speed / 1024:.0f} KB/s'
                        total_str = f'{total_size / 1024 / 1024:.1f} MB'

                        task['title'] = label
                        task['progress_pct'] = pct
                        task['speed'] = speed_str
                        task['eta'] = ''
                    else:
                        task['title'] = label
                        task['progress_pct'] = min(round(downloaded / (1024 * 1024), 1), 99.0)

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


def _is_likely_fmp4_url(url):
    """Check if the URL likely serves fragmented MP4 (fMP4).

    Kuaishou uses vod-rt-remux/hls-ts path for HLS-to-MP4 remux,
    which produces fragmented MP4 that can't play/seek in Android gallery.
    """
    return 'vod-rt-remux' in url or 'hls-ts' in url or 'REALTIME_REMUX' in url


def _download_hls(url, filepath, task, label=''):
    """Download an HLS stream using yt-dlp, then apply faststart."""
    try:
        import yt_dlp
    except ImportError:
        logger.warning('yt-dlp not available, cannot download HLS stream')
        return False

    try:
        out_dir = os.path.dirname(filepath)
        # Use safe temp name without special chars that break yt-dlp
        temp_name = f'kuaishou_hls_{int(time.time())}'
        temp_path = os.path.join(out_dir, f'{temp_name}.mp4')

        def _progress_hook(d):
            if task.get('status') == 'cancelled':
                raise yt_dlp.utils.DownloadError('cancelled')
            if d.get('status') == 'downloading':
                total = max(d.get('total_bytes', 1), d.get('total_bytes_estimate', 1))
                pct = d.get('downloaded_bytes', 0) / max(total, 1) * 100
                task['title'] = label
                task['progress_pct'] = round(pct, 1)
            elif d.get('status') == 'finished':
                task['title'] = label
                task['progress_pct'] = 100.0

        # Download without yt-dlp postprocessor (faststart applied separately after)
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

        # Post-processing (fMP4 conversion, duration fix, faststart)
        # is handled by _faststart() in _download_video after this returns

        filesize = os.path.getsize(filepath)
        task['title'] = label
        task['progress_pct'] = 100.0
        task['speed'] = ''
        task['eta'] = ''
        return True

    except yt_dlp.utils.DownloadError as e:
        if 'cancelled' in str(e).lower():
            return False
        logger.warning(f'yt-dlp HLS download failed: {e}')
    except Exception as e:
        logger.warning(f'yt-dlp HLS download exception: {e}')

    return False


def _find_ffmpeg():
    """Find ffmpeg binary on Android (same pattern as bilibili.py)."""
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        return ffmpeg
    for p in ['/data/data/com.ytdlp.webui/files/ffmpeg',
              '/data/local/tmp/ffmpeg']:
        if os.path.exists(p):
            return p
    return None


def _faststart_ffmpeg(filepath):
    """Use ffmpeg to move moov atom to front of MP4 file."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return False
    tmp_path = f'{filepath}.tmp.mp4'
    cmd = [ffmpeg, '-y', '-i', filepath, '-c', 'copy',
           '-movflags', '+faststart', tmp_path]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode == 0 and os.path.exists(tmp_path):
            os.replace(tmp_path, filepath)
            logger.info(f'FFmpeg faststart applied: {filepath}')
            return True
        else:
            stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
            logger.warning(f'FFmpeg faststart failed: {stderr[:200]}')
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    except Exception as e:
        logger.warning(f'FFmpeg faststart error: {e}')
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return False


def _faststart_python(filepath):
    """Pure Python moov atom mover (qt-faststart), no external dependencies.

    Moves the moov atom from the end of the file to the beginning (after ftyp),
    and updates stco/stco2 chunk offsets accordingly.
    """
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
    except Exception as e:
        logger.warning(f'Python faststart read error: {e}')
        return False

    if len(data) < 16:
        return False

    # Parse top-level boxes
    pos = 0
    boxes = []
    while pos + 8 <= len(data):
        size = struct.unpack('>I', data[pos:pos + 4])[0]
        box_type = data[pos + 4:pos + 8]
        header_size = 8
        if size == 1:
            if pos + 16 > len(data):
                break
            size = struct.unpack('>Q', data[pos + 8:pos + 16])[0]
            header_size = 16
        elif size == 0:
            size = len(data) - pos
        boxes.append((pos, size, box_type, header_size))
        pos += size

    # Find ftyp, moov, mdat
    ftyp_info = None
    moov_info = None
    mdat_info = None
    for offset, size, btype, hsize in boxes:
        if btype == b'ftyp' and ftyp_info is None:
            ftyp_info = (offset, size, hsize)
        elif btype == b'moov' and moov_info is None:
            moov_info = (offset, size, hsize)
        elif btype == b'mdat' and mdat_info is None:
            mdat_info = (offset, size, hsize)

    if not moov_info or not mdat_info:
        logger.warning('Python faststart: moov or mdat not found')
        return False

    # If moov is already before mdat, no action needed
    if moov_info[0] < mdat_info[0]:
        logger.info('Python faststart: moov already before mdat, skipping')
        return True

    moov_offset, moov_size, moov_header = moov_info

    # Update chunk offsets in stco/stco2 within moov
    # delta = moov_size (everything after ftyp shifts by moov_size)
    delta = moov_size
    moov_data = bytearray(data[moov_offset:moov_offset + moov_size])

    def _update_stco(atom_data, start, end):
        """Update chunk offset table within a stco or stco2 atom."""
        if end - start < 8:
            return
        version = atom_data[start + 8]  # version byte
        entry_count = struct.unpack('>I', atom_data[start + 12:start + 16])[0]
        offset_pos = start + 16
        for _ in range(entry_count):
            if offset_pos + 4 > end:
                break
            old_val = struct.unpack('>I', atom_data[offset_pos:offset_pos + 4])[0]
            new_val = old_val + delta
            struct.pack_into('>I', atom_data, offset_pos, new_val)
            offset_pos += 4

    def _update_stco2(atom_data, start, end):
        """Update chunk offset table within a stco2 (64-bit) atom."""
        if end - start < 8:
            return
        entry_count = struct.unpack('>I', atom_data[start + 12:start + 16])[0]
        offset_pos = start + 16
        for _ in range(entry_count):
            if offset_pos + 8 > end:
                break
            old_val = struct.unpack('>Q', atom_data[offset_pos:offset_pos + 8])[0]
            new_val = old_val + delta
            struct.pack_into('>Q', atom_data, offset_pos, new_val)
            offset_pos += 8

    # Recursively find stco/stco2 atoms within moov
    def _find_and_update_atoms(atom_data, start, end, depth=0):
        if depth > 10:
            return
        pos = start
        while pos + 8 <= end:
            size = struct.unpack('>I', atom_data[pos:pos + 4])[0]
            atype = atom_data[pos + 4:pos + 8]
            header = 8
            if size == 1:
                if pos + 16 > end:
                    break
                size = struct.unpack('>Q', atom_data[pos + 8:pos + 16])[0]
                header = 16
            elif size == 0:
                size = end - pos
            if size < 8:
                break
            atom_end = pos + size
            if atom_end > end:
                atom_end = end

            if atype == b'stco':
                _update_stco(atom_data, pos, atom_end)
            elif atype == b'co64':
                _update_stco2(atom_data, pos, atom_end)
            else:
                # Recurse into container atoms
                if atype in (b'trak', b'mdia', b'minf', b'stbl', b'stbl',
                            b'moov', b'udta', b'ilist', b'edts', b'uuid'):
                    _find_and_update_atoms(atom_data, pos + header, atom_end, depth + 1)

            pos = atom_end

    _find_and_update_atoms(moov_data, moov_header, moov_size, 0)

    # Build new file: ftyp + moov (updated) + all other boxes (in original order, excluding ftyp and moov)
    new_data = bytearray()
    for offset, size, btype, hsize in boxes:
        if btype == b'ftyp':
            new_data.extend(data[offset:offset + size])
        elif offset == moov_offset:
            new_data.extend(moov_data)
        else:
            new_data.extend(data[offset:offset + size])

    # Write the new file
    tmp_path = f'{filepath}.faststart.tmp'
    try:
        with open(tmp_path, 'wb') as f:
            f.write(new_data)
        os.replace(tmp_path, filepath)
        logger.info(f'Python faststart applied: {filepath}')
        return True
    except Exception as e:
        logger.warning(f'Python faststart write error: {e}')
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def _is_fragmented_mp4(filepath):
    """Check if the file is a fragmented MP4 (has moof boxes)."""
    try:
        with open(filepath, 'rb') as f:
            header = f.read(65536)
        return b'moof' in header
    except Exception:
        return False


def _remux_android(filepath):
    """Convert fMP4/TS to standard MP4 using Android native MediaMuxer.

    Uses MediaExtractor to read samples and MediaMuxer to write standard MP4.
    Very low memory usage (~2MB buffer). Produces standard MP4 with proper
    stbl for seeking and gallery compatibility.
    """
    try:
        from com.ytdlp.webui import MediaMuxerHelper
        tmp_path = filepath + '.remux.tmp'
        logger.info('Trying Android native remux to standard MP4...')
        if MediaMuxerHelper.remux(filepath, tmp_path):
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1024:
                os.replace(tmp_path, filepath)
                logger.info('Native remux succeeded: converted to standard MP4')
                return True
            else:
                logger.warning('Remux output too small, discarding')
        else:
            logger.warning('Native remux returned false')
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except ImportError:
        pass  # Not on Android or Chaquopy not available
    except Exception as e:
        logger.warning(f'Remux error: {e}')
        tmp_path = filepath + '.remux.tmp'
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return False


def _convert_with_ffmpeg_helper(filepath):
    """Convert to standard MP4 using bundled FFmpegKit (Android).

    Uses stream copy (-c copy) — no re-encoding, very fast.
    Converts fMP4/TS to standard MP4 with proper stbl and moov at front.
    """
    try:
        from com.ytdlp.webui import FFmpegHelper
        tmp_path = filepath + '.ffmpeg.tmp'
        logger.info('Trying FFmpegKit conversion...')
        if FFmpegHelper.convertToMp4(filepath, tmp_path):
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1024:
                os.replace(tmp_path, filepath)
                logger.info('FFmpegKit conversion succeeded: standard MP4')
                return True
            else:
                logger.warning('FFmpegKit output too small')
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except ImportError:
        pass  # Not on Android or FFmpegKit not bundled
    except Exception as e:
        logger.warning(f'FFmpegKit error: {e}')
        tmp_path = filepath + '.ffmpeg.tmp'
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return False


def _faststart(filepath):
    """Ensure the file is a standard MP4 with moov at front for mobile playback.

    Converts fMP4/TS to standard MP4 if needed (for gallery compatibility and seeking).

    Strategy (ordered by reliability):
    1. FFmpegKit (bundled in APK, handles ALL formats — fMP4, TS, etc.)
    2. System ffmpeg (if available on device, e.g., rooted or PC)
    3. Android MediaMuxer (for fMP4, low memory native fallback)
    4. Python moov mover (for standard MP4 that just needs moov at front)
    """
    if not filepath.endswith('.mp4'):
        return

    # Strategy 1: FFmpegKit (bundled, most reliable, handles all formats)
    if _convert_with_ffmpeg_helper(filepath):
        return

    # Strategy 2: System ffmpeg (if available on device)
    if _faststart_ffmpeg(filepath):
        return

    # Strategy 3: Android MediaMuxer (for fMP4 files, native fallback)
    if _is_fragmented_mp4(filepath):
        if _remux_android(filepath):
            return  # Converted to standard MP4, done
        # MediaMuxer failed, at least fix duration for playback
        logger.warning('All conversion methods failed, patching duration only')
        _patch_fmp4_duration(filepath)
        return

    # Strategy 4: Python moov mover (for standard MP4 that needs moov at front)
    _faststart_python(filepath)


def _patch_fmp4_duration(filepath):
    """Patch duration=0 in fMP4 moov in-place (minimal memory).

    Only fixes duration display, does NOT fix seeking.
    Used as last-resort fallback.
    """
    if not filepath.endswith('.mp4') or not os.path.exists(filepath):
        return

    try:
        with open(filepath, 'r+b') as f:
            data = bytearray(f.read())
    except Exception as e:
        logger.warning(f'duration patch: read error: {e}')
        return

    n = len(data)
    if n < 16:
        return

    pos = 0
    moov_offset = None
    moov_size = 0
    while pos + 8 <= n:
        size = struct.unpack('>I', data[pos:pos+4])[0]
        btype = data[pos+4:pos+8]
        if size == 1:
            if pos + 16 > n:
                break
            size = struct.unpack('>Q', data[pos+8:pos+16])[0]
        elif size == 0:
            size = n - pos
        if btype == b'moov':
            moov_offset = pos
            moov_size = size
            break
        pos += size

    if moov_offset is None:
        return

    p = moov_offset + 8
    mvhd_ts = 0
    mvhd_dur_off = None
    mvhd_dur_sz = 4
    track_info = {}
    trex_defaults = {}

    while p + 8 <= moov_offset + moov_size:
        s = struct.unpack('>I', data[p:p+4])[0]
        t = data[p+4:p+8]
        if s < 8:
            break

        if t == b'mvhd':
            version = data[p+8]
            if version == 0:
                mvhd_ts = struct.unpack('>I', data[p+8+12:p+8+16])[0]
                mvhd_dur_off = p + 8 + 16
                mvhd_dur_sz = 4
            else:
                mvhd_ts = struct.unpack('>I', data[p+8+20:p+8+24])[0]
                mvhd_dur_off = p + 8 + 24
                mvhd_dur_sz = 8
        elif t == b'trak':
            tp = p + 8
            track_id = None
            while tp + 8 <= p + s:
                ts2 = struct.unpack('>I', data[tp:tp+4])[0]
                tt2 = data[tp+4:tp+8]
                if ts2 < 8:
                    break
                if tt2 == b'tkhd':
                    ver = data[tp+8]
                    if ver == 0:
                        track_id = struct.unpack('>I', data[tp+8+12:tp+8+16])[0]
                    else:
                        track_id = struct.unpack('>I', data[tp+8+20:tp+8+24])[0]
                elif tt2 == b'mdia':
                    mp = tp + 8
                    while mp + 8 <= tp + ts2:
                        ms2 = struct.unpack('>I', data[mp:mp+4])[0]
                        mt2 = data[mp+4:mp+8]
                        if ms2 < 8:
                            break
                        if mt2 == b'mdhd':
                            ver = data[mp+8]
                            if ver == 0:
                                ts_val = struct.unpack('>I', data[mp+8+12:mp+8+16])[0]
                                track_info[track_id] = [ts_val, mp+8+16, 4]
                            else:
                                ts_val = struct.unpack('>I', data[mp+8+20:mp+8+24])[0]
                                track_info[track_id] = [ts_val, mp+8+24, 8]
                        mp += ms2
                tp += ts2
        elif t == b'mvex':
            tp = p + 8
            while tp + 8 <= p + s:
                ts2 = struct.unpack('>I', data[tp:tp+4])[0]
                tt2 = data[tp+4:tp+8]
                if ts2 < 8:
                    break
                if tt2 == b'trex':
                    tid = struct.unpack('>I', data[tp+12:tp+16])[0]
                    dd = struct.unpack('>I', data[tp+16:tp+20])[0]
                    trex_defaults[tid] = dd
                tp += ts2
        p += s

    if mvhd_ts == 0:
        return

    track_durations = {}
    pos = 0
    while pos + 8 <= n:
        size = struct.unpack('>I', data[pos:pos+4])[0]
        btype = data[pos+4:pos+8]
        if size == 1:
            if pos + 16 > n:
                break
            size = struct.unpack('>Q', data[pos+8:pos+16])[0]
        elif size == 0:
            size = n - pos
        if size < 8:
            break

        if btype == b'moof':
            mp = pos + 8
            while mp + 8 <= pos + size:
                ms = struct.unpack('>I', data[mp:mp+4])[0]
                mt = data[mp+4:mp+8]
                if ms < 8:
                    break
                if mt == b'traf':
                    cur_tid = 0
                    tf_dd = 0
                    tp = mp + 8
                    while tp + 8 <= mp + ms:
                        ts2 = struct.unpack('>I', data[tp:tp+4])[0]
                        tt2 = data[tp+4:tp+8]
                        if ts2 < 8:
                            break
                        if tt2 == b'tfhd':
                            fl = struct.unpack('>I', data[tp+8:tp+12])[0]
                            cur_tid = struct.unpack('>I', data[tp+12:tp+16])[0]
                            off = tp + 16
                            if fl & 0x01:
                                off += 8
                            if fl & 0x02:
                                off += 4
                            if fl & 0x08:
                                tf_dd = struct.unpack('>I', data[off:off+4])[0]
                        elif tt2 == b'trun':
                            fl = struct.unpack('>I', data[tp+8:tp+12])[0]
                            sc = struct.unpack('>I', data[tp+12:tp+16])[0]
                            off = tp + 16
                            if fl & 0x001:
                                off += 4
                            if fl & 0x004:
                                off += 4
                            esz = 0
                            if fl & 0x100: esz += 4
                            if fl & 0x200: esz += 4
                            if fl & 0x400: esz += 4
                            if fl & 0x800: esz += 4
                            frag_dur = 0
                            if fl & 0x100:
                                for _ in range(sc):
                                    if off + esz > tp + ts2:
                                        break
                                    frag_dur += struct.unpack('>I', data[off:off+4])[0]
                                    off += esz
                            else:
                                dd = tf_dd or trex_defaults.get(cur_tid, 0)
                                frag_dur = dd * sc
                            track_durations.setdefault(cur_tid, 0)
                            track_durations[cur_tid] += frag_dur
                        tp += ts2
                mp += ms
        pos += size

    if not track_durations:
        return

    max_sec = 0
    for tid, dur in track_durations.items():
        if tid in track_info:
            ts_val = track_info[tid][0]
            if ts_val > 0:
                sec = dur / ts_val
                if sec > max_sec:
                    max_sec = sec

    if max_sec <= 0:
        return

    new_mvhd_dur = int(max_sec * mvhd_ts)
    if mvhd_dur_sz == 4:
        struct.pack_into('>I', data, mvhd_dur_off, new_mvhd_dur)
    else:
        struct.pack_into('>Q', data, mvhd_dur_off, new_mvhd_dur)

    for tid, dur in track_durations.items():
        if tid in track_info:
            _, dur_off, dur_sz = track_info[tid]
            if dur_sz == 4:
                struct.pack_into('>I', data, dur_off, dur)
            else:
                struct.pack_into('>Q', data, dur_off, dur)

    try:
        with open(filepath, 'wb') as f:
            f.write(data)
        logger.info(f'fMP4 duration patched: {max_sec:.1f}s ({max_sec/60:.1f}min)')
    except Exception as e:
        logger.warning(f'duration patch: write error: {e}')


def _build_seek_table(filepath):
    """Build sample table (stbl) in moov for fMP4 seeking.

    HLS downloads produce fragmented MP4 (fMP4) where moov has empty stbl
    (stts/stsz/stsc/stco with 0 entries). Mobile players cannot seek without
    a sample table. This function:
    1. Parses all moof/trun boxes to collect per-sample data
    2. Patches mvhd/mdhd duration fields (fixes 0-duration issue)
    3. Builds complete stbl (stts/stsz/stsc/stco/stss) for each track
    4. Replaces empty stbl in moov, removes mvex
    5. Adjusts stco offsets for the new moov size
    Returns True on success, False on failure.
    """
    if not filepath.endswith('.mp4') or not os.path.exists(filepath):
        return False

    try:
        with open(filepath, 'rb') as f:
            data = bytearray(f.read())
    except Exception as e:
        logger.warning(f'build_seek_table: read error: {e}')
        return False

    n = len(data)
    if n < 16:
        return False

    # Step 1: Parse top-level boxes
    pos = 0
    top_boxes = []
    while pos + 8 <= n:
        sz = struct.unpack('>I', data[pos:pos+4])[0]
        bt = data[pos+4:pos+8]
        if sz == 1:
            if pos + 16 > n:
                break
            sz = struct.unpack('>Q', data[pos+8:pos+16])[0]
        elif sz == 0:
            sz = n - pos
        top_boxes.append((pos, sz, bt))
        pos += sz

    moov_info = next((b for b in top_boxes if b[2] == b'moov'), None)
    if not moov_info:
        return False
    moov_off, moov_sz, _ = moov_info

    # Step 2: Parse moov: mvhd, traks, mvex/trex
    p = moov_off + 8
    mvhd_ts = 0
    mvhd_dur_off = 0
    mvhd_dur_sz = 4
    traks = []
    trex = {}

    while p + 8 <= moov_off + moov_sz:
        s = struct.unpack('>I', data[p:p+4])[0]
        t = data[p+4:p+8]
        if s < 8:
            break

        if t == b'mvhd':
            ver = data[p+8]
            if ver == 0:
                mvhd_ts = struct.unpack('>I', data[p+8+12:p+8+16])[0]
                mvhd_dur_off = p + 8 + 16
                mvhd_dur_sz = 4
            else:
                mvhd_ts = struct.unpack('>I', data[p+8+20:p+8+24])[0]
                mvhd_dur_off = p + 8 + 24
                mvhd_dur_sz = 8

        elif t == b'trak':
            ti = {'trak_off': p, 'trak_sz': s, 'tid': None,
                  'stsd_off': 0, 'stsd_sz': 0,
                  'mdhd_ts': 0, 'mdhd_dur_off': 0, 'mdhd_dur_sz': 4}
            tp = p + 8
            while tp + 8 <= p + s:
                ts2 = struct.unpack('>I', data[tp:tp+4])[0]
                tt2 = data[tp+4:tp+8]
                if ts2 < 8:
                    break

                if tt2 == b'tkhd':
                    ver = data[tp+8]
                    off = tp+8+12 if ver == 0 else tp+8+20
                    ti['tid'] = struct.unpack('>I', data[off:off+4])[0]

                elif tt2 == b'mdia':
                    mp = tp + 8
                    while mp + 8 <= tp + ts2:
                        ms2 = struct.unpack('>I', data[mp:mp+4])[0]
                        mt2 = data[mp+4:mp+8]
                        if ms2 < 8:
                            break

                        if mt2 == b'mdhd':
                            ver = data[mp+8]
                            if ver == 0:
                                ti['mdhd_ts'] = struct.unpack('>I', data[mp+8+12:mp+8+16])[0]
                                ti['mdhd_dur_off'] = mp + 8 + 16
                                ti['mdhd_dur_sz'] = 4
                            else:
                                ti['mdhd_ts'] = struct.unpack('>I', data[mp+8+20:mp+8+24])[0]
                                ti['mdhd_dur_off'] = mp + 8 + 24
                                ti['mdhd_dur_sz'] = 8

                        elif mt2 == b'minf':
                            np2 = mp + 8
                            while np2 + 8 <= mp + ms2:
                                ns2 = struct.unpack('>I', data[np2:np2+4])[0]
                                nt2 = data[np2+4:np2+8]
                                if ns2 < 8:
                                    break
                                if nt2 == b'stbl':
                                    sp = np2 + 8
                                    while sp + 8 <= np2 + ns2:
                                        ss2 = struct.unpack('>I', data[sp:sp+4])[0]
                                        st2 = data[sp+4:sp+8]
                                        if ss2 < 8:
                                            break
                                        if st2 == b'stsd':
                                            ti['stsd_off'] = sp
                                            ti['stsd_sz'] = ss2
                                        sp += ss2
                                np2 += ns2
                        mp += ms2
                tp += ts2
            traks.append(ti)

        elif t == b'mvex':
            tp = p + 8
            while tp + 8 <= p + s:
                ts2 = struct.unpack('>I', data[tp:tp+4])[0]
                tt2 = data[tp+4:tp+8]
                if ts2 < 8:
                    break
                if tt2 == b'trex':
                    tid = struct.unpack('>I', data[tp+12:tp+16])[0]
                    trex[tid] = (struct.unpack('>I', data[tp+16:tp+20])[0],
                                 struct.unpack('>I', data[tp+20:tp+24])[0])
                tp += ts2

        p += s

    if mvhd_ts == 0:
        logger.warning('build_seek_table: mvhd timescale=0')
        return False

    # Step 3: Parse moof boxes: collect per-track sample data
    track_frags = {}
    for tpos, tsize, tbtype in top_boxes:
        if tbtype != b'moof':
            continue
        mp = tpos + 8
        while mp + 8 <= tpos + tsize:
            ms = struct.unpack('>I', data[mp:mp+4])[0]
            mt = data[mp+4:mp+8]
            if ms < 8:
                break

            if mt == b'traf':
                cur_tid = 0
                tf_dd = 0
                tf_ds = 0
                tp = mp + 8
                while tp + 8 <= mp + ms:
                    ts2 = struct.unpack('>I', data[tp:tp+4])[0]
                    tt2 = data[tp+4:tp+8]
                    if ts2 < 8:
                        break

                    if tt2 == b'tfhd':
                        fl = struct.unpack('>I', data[tp+8:tp+12])[0]
                        cur_tid = struct.unpack('>I', data[tp+12:tp+16])[0]
                        off = tp + 16
                        if fl & 0x01:
                            off += 8
                        if fl & 0x02:
                            off += 4
                        if fl & 0x08:
                            tf_dd = struct.unpack('>I', data[off:off+4])[0]
                            off += 4
                        if fl & 0x10:
                            tf_ds = struct.unpack('>I', data[off:off+4])[0]

                    elif tt2 == b'trun':
                        fl = struct.unpack('>I', data[tp+8:tp+12])[0]
                        sc = struct.unpack('>I', data[tp+12:tp+16])[0]
                        doff = 0
                        off = tp + 16
                        if fl & 0x001:
                            doff = struct.unpack('>I', data[off:off+4])[0]
                            off += 4
                        if fl & 0x004:
                            off += 4
                        esz = 0
                        hd = bool(fl & 0x100)
                        hs = bool(fl & 0x200)
                        hf = bool(fl & 0x400)
                        hc = bool(fl & 0x800)
                        if hd:
                            esz += 4
                        if hs:
                            esz += 4
                        if hf:
                            esz += 4
                        if hc:
                            esz += 4
                        sizes = []
                        durs = []
                        for _ in range(sc):
                            if off + esz > tp + ts2:
                                break
                            eo = off
                            if hd:
                                durs.append(struct.unpack('>I', data[eo:eo+4])[0])
                                eo += 4
                            if hs:
                                sizes.append(struct.unpack('>I', data[eo:eo+4])[0])
                                eo += 4
                            off += esz
                        dd = tf_dd or trex.get(cur_tid, (0, 0))[0]
                        ds = tf_ds or trex.get(cur_tid, (0, 0))[1]
                        abs_off = tpos + doff if doff else 0
                        frag = {'sc': sc, 'sizes': sizes, 'durs': durs,
                                'hs': hs, 'hd': hd, 'dd': dd, 'ds': ds,
                                'abs_off': abs_off}
                        track_frags.setdefault(cur_tid, []).append(frag)
                    tp += ts2
            mp += ms

    if not track_frags:
        logger.warning('build_seek_table: no moof fragments found')
        return False

    # Step 4: Calculate total durations per track
    track_total = {}
    for tid, frags in track_frags.items():
        total = 0
        for f in frags:
            if f['hd']:
                total += sum(f['durs'])
            else:
                total += f['dd'] * f['sc']
        track_total[tid] = total

    # Step 5: Patch durations in original data
    max_sec = 0
    for tid, dur in track_total.items():
        for ti in traks:
            if ti['tid'] == tid and ti['mdhd_ts'] > 0:
                sec = dur / ti['mdhd_ts']
                if sec > max_sec:
                    max_sec = sec

    if max_sec <= 0:
        logger.warning('build_seek_table: duration=0')
        return False

    new_mvhd_dur = int(max_sec * mvhd_ts)
    if mvhd_dur_sz == 4:
        struct.pack_into('>I', data, mvhd_dur_off, new_mvhd_dur)
    else:
        struct.pack_into('>Q', data, mvhd_dur_off, new_mvhd_dur)

    for tid, dur in track_total.items():
        for ti in traks:
            if ti['tid'] == tid:
                if ti['mdhd_dur_sz'] == 4:
                    struct.pack_into('>I', data, ti['mdhd_dur_off'], dur)
                else:
                    struct.pack_into('>Q', data, ti['mdhd_dur_off'], dur)

    # Step 6: Build new stbl for each track
    new_stbls = {}
    for ti in traks:
        tid = ti['tid']
        if tid not in track_frags:
            continue
        frags = track_frags[tid]
        total = sum(f['sc'] for f in frags)

        # stts (time-to-sample)
        dd0 = frags[0]['dd']
        all_same = all(f['dd'] == dd0 for f in frags) and not any(f['hd'] for f in frags)
        if all_same:
            stts_e = [(total, dd0)]
        else:
            raw = []
            for f in frags:
                if f['hd']:
                    for d in f['durs']:
                        raw.append((1, d))
                else:
                    raw.append((f['sc'], f['dd']))
            stts_e = []
            for c, d in raw:
                if stts_e and stts_e[-1][1] == d:
                    stts_e[-1] = (stts_e[-1][0] + c, d)
                else:
                    stts_e.append([c, d])
            stts_e = [tuple(x) for x in stts_e]
        stts = struct.pack('>I', 16 + len(stts_e) * 8) + b'stts' + struct.pack('>II', 0, len(stts_e))
        for c, d in stts_e:
            stts += struct.pack('>II', c, d)

        # stsz (sample sizes)
        if any(f['hs'] for f in frags):
            stsz = struct.pack('>I', 20 + total * 4) + b'stsz' + struct.pack('>III', 0, 0, total)
            for f in frags:
                if f['hs']:
                    for sz in f['sizes']:
                        stsz += struct.pack('>I', sz)
                else:
                    for _ in range(f['sc']):
                        stsz += struct.pack('>I', f['ds'])
        else:
            stsz = struct.pack('>I', 20) + b'stsz' + struct.pack('>III', 0, frags[0]['ds'], total)

        # stsc (sample-to-chunk)
        stsc_d = b''
        for i, f in enumerate(frags):
            stsc_d += struct.pack('>III', i + 1, f['sc'], 1)
        stsc = struct.pack('>I', 16 + len(frags) * 12) + b'stsc' + struct.pack('>II', 0, len(frags)) + stsc_d

        # stco (chunk offsets - will be patched with delta later)
        stco_d = b''
        for f in frags:
            stco_d += struct.pack('>I', f['abs_off'])
        stco = struct.pack('>I', 16 + len(frags) * 4) + b'stco' + struct.pack('>II', 0, len(frags)) + stco_d

        # stss (sync samples / keyframes: first sample of each fragment)
        stss_d = b''
        si = 0
        for f in frags:
            stss_d += struct.pack('>I', si + 1)
            si += f['sc']
        stss = struct.pack('>I', 16 + len(frags) * 4) + b'stss' + struct.pack('>II', 0, len(frags)) + stss_d

        # Assemble stbl: keep original stsd + new tables
        stsd = bytes(data[ti['stsd_off']:ti['stsd_off'] + ti['stsd_sz']])
        stbl_body = stsd + stts + stsc + stsz + stco + stss
        stbl = struct.pack('>I', len(stbl_body) + 8) + b'stbl' + stbl_body
        new_stbls[tid] = stbl

    # Step 7: Build new moov: replace stbl in traks, remove mvex
    def _replace_stbl_in_container(buf, off, sz, new_stbl):
        result = b''
        p2 = off + 8
        while p2 + 8 <= off + sz:
            s2 = struct.unpack('>I', buf[p2:p2+4])[0]
            t2 = buf[p2+4:p2+8]
            if s2 < 8:
                break
            if t2 == b'stbl':
                result += new_stbl
            elif t2 in (b'trak', b'mdia', b'minf'):
                inner = _replace_stbl_in_container(buf, p2, s2, new_stbl)
                result += inner
            else:
                result += bytes(buf[p2:p2+s2])
            p2 += s2
        return struct.pack('>I', len(result) + 8) + bytes(buf[off+4:off+8]) + result

    new_moov_body = b''
    p = moov_off + 8
    while p + 8 <= moov_off + moov_sz:
        s = struct.unpack('>I', data[p:p+4])[0]
        t = data[p+4:p+8]
        if s < 8:
            break

        if t == b'trak':
            ti = next((x for x in traks if x['trak_off'] == p), None)
            if ti and ti['tid'] in new_stbls:
                new_trak = _replace_stbl_in_container(data, p, s, new_stbls[ti['tid']])
                new_moov_body += new_trak
            else:
                new_moov_body += bytes(data[p:p+s])
        elif t == b'mvex':
            pass  # remove mvex (no longer fragmented)
        else:
            new_moov_body += bytes(data[p:p+s])
        p += s

    new_moov_sz = len(new_moov_body) + 8
    new_moov = bytearray(struct.pack('>I', new_moov_sz) + b'moov' + new_moov_body)
    delta = new_moov_sz - moov_sz

    # Step 8: Add delta to all stco entries in new moov
    def _patch_stco(buf, start, end, delta_val):
        pos2 = start
        while pos2 + 8 <= end:
            sz = struct.unpack('>I', buf[pos2:pos2+4])[0]
            bt = buf[pos2+4:pos2+8]
            if sz < 8 or pos2 + sz > end:
                break
            if bt == b'stco':
                cnt = struct.unpack('>I', buf[pos2+12:pos2+16])[0]
                for i in range(cnt):
                    off = pos2 + 16 + i * 4
                    if off + 4 <= end:
                        val = struct.unpack('>I', buf[off:off+4])[0]
                        if val > 0:
                            struct.pack_into('>I', buf, off, val + delta_val)
            elif bt in (b'moov', b'trak', b'mdia', b'minf', b'stbl'):
                _patch_stco(buf, pos2 + 8, pos2 + sz, delta_val)
            pos2 += sz

    _patch_stco(new_moov, 8, len(new_moov), delta)

    # Step 9: Build new file: ftyp + new_moov + everything after old moov
    ftyp = bytes(next((data[tp:tp+ts] for tp, ts, tb in top_boxes if tb == b'ftyp'), b''))
    after_moov = bytes(data[moov_off + moov_sz:])
    new_file = ftyp + bytes(new_moov) + after_moov

    # Step 10: Write to temp file, then replace original
    tmp_path = filepath + '.seek.tmp'
    try:
        with open(tmp_path, 'wb') as f:
            f.write(new_file)
        os.replace(tmp_path, filepath)
        logger.info(f'fMP4 seek table built: {max_sec:.1f}s ({max_sec/60:.1f}min), '
                     f'moov {moov_sz}->{new_moov_sz} bytes')
        return True
    except Exception as e:
        logger.warning(f'build_seek_table: write error: {e}')
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def _download_images(info, download_dir, safe_title, task):
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
        if task.get('status') == 'cancelled':
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
        task['title'] = label
        task['progress_pct'] = round((i / total) * 100, 1)

        if _download_file(img_url, filepath, task, label):
            total_size += os.path.getsize(filepath)
            # Update progress after each image download completes
            task['progress_pct'] = round(((i + 1) / total) * 100, 1)
        else:
            if task.get('status') == 'cancelled':
                return {'error': 'cancelled'}
            logger.warning(f'Failed to download image {i + 1}/{total}: {img_url}')

    task['title'] = safe_title
    task['progress_pct'] = 100.0
    task['speed'] = ''
    task['eta'] = ''

    return {
        'title': info.get('title', ''),
        'filepath': folder_path,
        'filesize': total_size,
        'author': info.get('author', ''),
        'thumbnail': info.get('cover_url'),
        'type': 'images',
        'image_count': total,
    }


def _download_video(info, download_dir, safe_title, task):
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

    # Build ordered list: standard MP4 first, then fMP4-looking URLs, then HLS last
    # Standard MP4 URLs (photo-video-mz, mainMvUrls CDN) work best on mobile
    # vod-rt-remux/hls-ts URLs serve fragmented MP4 (fMP4) despite .mp4 extension
    standard_mp4 = []
    fmp4_urls = []
    hls_urls = []
    seen = set()
    for u in [best_url] + video_urls:
        if not u or u in seen:
            continue
        seen.add(u)
        if _is_hls_url(u):
            hls_urls.append(u)
        elif _is_likely_fmp4_url(u):
            fmp4_urls.append(u)
        else:
            standard_mp4.append(u)
    urls_to_try = standard_mp4 + fmp4_urls + hls_urls
    if urls_to_try:
        logger.info(f'URL priority: {len(standard_mp4)} standard MP4, '
                     f'{len(fmp4_urls)} fMP4, {len(hls_urls)} HLS')

    task['title'] = title
    task['progress_pct'] = 0.0

    for video_url in urls_to_try:
        if task.get('status') == 'cancelled':
            return {'error': 'cancelled'}

        downloaded = False

        # Handle HLS streams (.m3u8) with yt-dlp
        if _is_hls_url(video_url):
            downloaded = _download_hls(
                video_url, filepath, task, title
            )
        else:
            downloaded = _download_file(
                video_url, filepath, task, title
            )

        if downloaded:
            filesize = os.path.getsize(filepath)

            # Apply faststart: move moov atom to front for mobile playback
            _faststart(filepath)
            thumbnail = info.get('cover_url', '')

            task['title'] = title
            task['progress_pct'] = 100.0
            task['speed'] = ''
            task['eta'] = ''

            return {
                'title': info.get('title', ''),
                'filepath': filepath,
                'filesize': filesize,
                'author': info.get('author', ''),
                'thumbnail': thumbnail,
            }

    return {'error': 'All video URLs failed to download'}


def _download_kuaishou_direct(task, url, download_dir):
    """Download Kuaishou video/images using full HTML parsing logic."""
    task['status'] = 'starting'
    task['title'] = '正在解析快手链接...'

    info = fetch_kuaishou_info(url)
    if 'error' in info:
        raise Exception(info['error'])

    title = info.get('title', 'untitled') or 'untitled'
    safe_title = re.sub(r'[<>\":/\\|?*\n\r\t]', '_', title)[:80].strip()
    # Strip trailing dots that produce confusing filenames like ....mp4
    safe_title = safe_title.strip('.').strip()
    if not safe_title or safe_title == 'untitled':
        safe_title = f'kuaishou_{info.get("content_id", "post")}'

    task['title'] = safe_title

    content_type = info.get('type', 'video')

    if content_type == 'images':
        result = _download_images(info, download_dir, safe_title, task)
    else:
        result = _download_video(info, download_dir, safe_title, task)

    if 'error' in result:
        if result['error'] == 'cancelled':
            task['status'] = 'cancelled'
            return
        raise Exception(result['error'])

    task['status'] = 'completed'
    task['progress_pct'] = 100.0
    task['filename'] = result['filepath']
    task['thumbnail'] = result.get('thumbnail', '') or ''
    task['speed'] = ''
    task['eta'] = ''

    logger.info(f"[Task {task['id']}] Download completed: {result['filepath']}")
