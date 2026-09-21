"""Android entry point for the embedded backend service."""

import asyncio
import json
import logging
import mimetypes
import os
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# Ensure app package is importable from this file's location
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils import (
    _get_download_dir,
    _extract_url,
    _detect_platform,
    _normalize_platform_url,
    _resolve_douyin_url,
    _fetch_douyin_ttwid,
    _log,
    _is_android,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("android-server")

_server = None
_thread = None
_startup_error = None
_server_ready = False
_full_server_ready = False
_android_context = None  # Set by Java via start(context)

# Download task tracking for minimal server
_download_tasks = {}
_task_counter = 0


def _get_android_context():
    """Get Android Context - stored by Java during start()."""
    global _android_context
    if _android_context is not None:
        return _android_context
    try:
        from java import jclass
        _android_context = jclass("com.chaquo.python.Python").getInstance().getPlatform().getContext()
    except Exception:
        pass
    return _android_context


_ERROR_LOG_PATH = "/data/data/com.ytdlp.webui/files/server_error.log"


def _write_error_log(msg):
    try:
        os.makedirs(os.path.dirname(_ERROR_LOG_PATH), exist_ok=True)
        with open(_ERROR_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


_COOKIE_DIR = "/data/data/com.ytdlp.webui/files/cookies"
_COOKIE_FILE = os.path.join(_COOKIE_DIR, "douyin_cookies.txt")


def _fetch_bilibili_cookies():
    """Fetch fresh cookies for Bilibili."""
    try:
        os.makedirs(_COOKIE_DIR, exist_ok=True)
        cookie_file = os.path.join(_COOKIE_DIR, "bilibili_cookies.txt")

        import urllib.request

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

        import http.cookiejar
        cookie_jar = http.cookiejar.MozillaCookieJar(cookie_file)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

        req = urllib.request.Request('https://www.bilibili.com/', headers=headers)
        try:
            resp = opener.open(req, timeout=10)
            resp.read()
            resp.close()
        except Exception:
            pass

        cookie_jar.save(ignore_discard=True, ignore_expires=True)
        _log(f"Saved Bilibili cookies to {cookie_file}")
        return cookie_file
    except Exception as e:
        _log(f"Failed to fetch Bilibili cookies: {e}")
        return None


def _fetch_xiaohongshu_cookies():
    """Fetch fresh cookies for Xiaohongshu."""
    try:
        os.makedirs(_COOKIE_DIR, exist_ok=True)
        cookie_file = os.path.join(_COOKIE_DIR, "xiaohongshu_cookies.txt")

        import urllib.request
        import http.cookiejar

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

        cookie_jar = http.cookiejar.MozillaCookieJar(cookie_file)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

        req = urllib.request.Request('https://www.xiaohongshu.com/', headers=headers)
        try:
            resp = opener.open(req, timeout=10)
            resp.read()
            resp.close()
        except Exception:
            pass

        cookie_jar.save(ignore_discard=True, ignore_expires=True)
        _log(f"Saved Xiaohongshu cookies to {cookie_file}")
        return cookie_file
    except Exception as e:
        _log(f"Failed to fetch Xiaohongshu cookies: {e}")
        return None


def _fetch_kuaishou_cookies():
    """Fetch fresh cookies for Kuaishou."""
    try:
        os.makedirs(_COOKIE_DIR, exist_ok=True)
        cookie_file = os.path.join(_COOKIE_DIR, "kuaishou_cookies.txt")

        import urllib.request
        import http.cookiejar

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }

        cookie_jar = http.cookiejar.MozillaCookieJar(cookie_file)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

        req = urllib.request.Request('https://www.kuaishou.com/', headers=headers)
        try:
            resp = opener.open(req, timeout=10)
            resp.read()
            resp.close()
        except Exception:
            pass

        cookie_jar.save(ignore_discard=True, ignore_expires=True)
        _log(f"Saved Kuaishou cookies to {cookie_file}")
        return cookie_file
    except Exception as e:
        _log(f"Failed to fetch Kuaishou cookies: {e}")
        return None


def _get_cookies_for_platform(platform):
    """Get cookie file for the specified platform."""
    if platform == 'bilibili':
        return _fetch_bilibili_cookies()
    elif platform == 'xiaohongshu':
        return _fetch_xiaohongshu_cookies()
    elif platform == 'kuaishou':
        return _fetch_kuaishou_cookies()
    return None


def _run_ytdlp_download(task_id, url, download_dir):
    """Run yt-dlp download in background thread with detailed logging."""
    global _download_tasks
    task = _download_tasks.get(task_id)
    if not task:
        _log(f"ERROR: Task {task_id} not found in _download_tasks")
        return

    try:
        _log(f"[Task {task_id}] Starting download thread")
        _log(f"[Task {task_id}] URL: {url}")
        _log(f"[Task {task_id}] Download dir: {download_dir}")

        task['status'] = 'starting'
        task['title'] = '正在初始化...'

        # Step 1: Import yt_dlp
        _log(f"[Task {task_id}] Step 1: Importing yt_dlp...")
        import yt_dlp
        _log(f"[Task {task_id}] yt_dlp imported successfully, version: {yt_dlp.version.__version__}")

        # Step 2: Define progress hook
        def progress_hook(d):
            try:
                if d['status'] == 'downloading':
                    task['status'] = 'downloading'
                    pct_str = d.get('_percent_str', '0%')
                    try:
                        pct = float(pct_str.rstrip('%').strip())
                    except Exception:
                        pct = 0.0
                    task['progress_pct'] = pct
                    task['speed'] = d.get('_speed_str')
                    task['eta'] = d.get('_eta_str')
                    task['filesize'] = d.get('_total_bytes_str')
                elif d['status'] == 'finished':
                    task['status'] = 'processing'
                    task['progress_pct'] = 100.0
                    _log(f"[Task {task_id}] Download finished, processing...")
            except Exception as e:
                _log(f"[Task {task_id}] Progress hook error: {e}")

        # Step 3: Detect platform and route to appropriate downloader
        platform = _detect_platform(url)
        _log(f"[Task {task_id}] Step 3: Detected platform: {platform}")

        # Douyin: use direct extraction (yt-dlp doesn't work for Douyin)
        if platform == 'douyin':
            _log(f"[Task {task_id}] Using direct Douyin downloader (no yt-dlp)")
            from app.platforms.douyin import _download_douyin_direct
            _download_douyin_direct(task, url, download_dir)
            return

        # Kuaishou: use direct extraction (yt-dlp KuaishouIE is broken)
        if platform == 'kuaishou':
            _log(f"[Task {task_id}] Using direct Kuaishou downloader (no yt-dlp)")
            from app.platforms.kuaishou import _download_kuaishou_direct
            _download_kuaishou_direct(task, url, download_dir)
            return

        # Xiaohongshu: use direct download (yt-dlp doesn't support image posts)
        if platform == 'xiaohongshu':
            _log(f"[Task {task_id}] Using direct Xiaohongshu downloader (no yt-dlp)")
            from app.platforms.xiaohongshu import _download_xiaohongshu_direct
            _download_xiaohongshu_direct(task, url, download_dir)
            return

        # Bilibili: use direct download (yt-dlp gets 412 errors)
        if platform == 'bilibili':
            _log(f"[Task {task_id}] Using direct Bilibili downloader (no yt-dlp)")
            from app.platforms.bilibili import _download_bilibili_direct
            _download_bilibili_direct(task, url, download_dir)
            return

        # Other platforms: resolve short URL and normalize for yt-dlp
        download_url = url
        cookie_file = None
        if platform != 'other':
            download_url, platform = _normalize_platform_url(url)
            if download_url != url:
                task['url'] = download_url
                _log(f"[Task {task_id}] URL normalized: '{url}' -> '{download_url}'")

            platform_names = {
                'bilibili': 'B站',
                'xiaohongshu': '小红书',
                'kuaishou': '快手',
            }
            platform_name = platform_names.get(platform, platform)
            _log(f"[Task {task_id}] Fetching fresh {platform_name} cookies...")
            task['status'] = 'starting'
            task['title'] = f'正在获取{platform_name}Cookies...'
            cookie_file = _get_cookies_for_platform(platform)
            if cookie_file:
                _log(f"[Task {task_id}] Got cookies at: {cookie_file}")
            else:
                _log(f"[Task {task_id}] Warning: Could not fetch {platform_name} cookies")

        # Step 4: Configure yt-dlp
        _log(f"[Task {task_id}] Step 4: Configuring YoutubeDL...")
        ydl_opts = {
            'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'quiet': False,
            'no_warnings': False,
        }

        if cookie_file and os.path.exists(cookie_file):
            ydl_opts['cookiefile'] = cookie_file

        # Step 5: Extract info and download
        _log(f"[Task {task_id}] Step 5: Extracting info and downloading: {download_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(download_url, download=True)
            if info:
                task['title'] = info.get('title', 'Unknown')
                task['filename'] = ydl.prepare_filename(info)
                task['thumbnail'] = info.get('thumbnail')
                _log(f"[Task {task_id}] Title: {task['title']}")
                _log(f"[Task {task_id}] Filename: {task['filename']}")

        task['status'] = 'completed'
        task['progress_pct'] = 100.0
        task['completed_at'] = time.time()
        _log(f"[Task {task_id}] Download completed successfully!")

    except Exception as e:
        import traceback
        error_msg = f"[Task {task_id}] Download failed: {type(e).__name__}: {e}"
        tb = traceback.format_exc()
        _log(error_msg)
        _log(tb)
        _write_error_log(error_msg)
        _write_error_log(tb)
        task['status'] = 'failed'
        task['error'] = str(e)
        task['completed_at'] = time.time()


def get_startup_error():
    return _startup_error


def is_server_ready():
    return _server_ready


def is_full_server_ready():
    return _full_server_ready


def start(context=None):
    global _thread, _startup_error, _server_ready, _full_server_ready, _android_context
    if context is not None:
        _android_context = context
    if _thread and _thread.is_alive():
        return
    _startup_error = None
    _server_ready = False
    _full_server_ready = False
    _thread = threading.Thread(target=_run_server, daemon=True, name="server-thread")
    _thread.start()
    _log("Server thread started")


def _run_server():
    global _server, _server_ready, _startup_error, _full_server_ready

    static_dir = None
    if _is_android():
        this_dir = os.path.dirname(os.path.abspath(__file__))
        parent = os.path.dirname(this_dir)
        candidates = [
            os.path.join(parent, "static"),
            os.path.join(this_dir, "static"),
            "/data/data/com.ytdlp.webui/files/python/static",
            "/data/data/com.ytdlp.webui/files/static",
        ]
        for candidate in candidates:
            if os.path.isdir(candidate):
                static_dir = candidate
                _log(f"Found static dir: {static_dir}")
                break

    # Phase 1: Start minimal stdlib server on port 8000 (fast startup)
    try:
        _log("Phase 1: Starting minimal stdlib server on port 8000...")
        _start_minimal_server(static_dir)
        _log("Minimal server READY on port 8000!")
    except Exception as e:
        error_msg = f"Minimal server failed: {type(e).__name__}: {e}"
        _startup_error = error_msg
        _log(error_msg)
        _write_error_log(error_msg)
        return

    # Phase 2: Start full FastAPI server on port 8001 (WebView prefers this)
    try:
        _log("Phase 2: Starting FastAPI server on port 8001...")

        _log("  Importing fastapi...")
        import fastapi
        _log(f"  fastapi {fastapi.__version__} OK")

        _log("  Importing uvicorn...")
        import uvicorn
        _log(f"  uvicorn {uvicorn.__version__} OK")

        _log("  Importing app.main...")
        from app.main import app as fastapi_app
        _log("  app.main imported OK")

        _log("  Starting uvicorn on port 8001...")
        loop = asyncio.new_event_loop()

        config = uvicorn.Config(
            fastapi_app,
            host="127.0.0.1",
            port=8001,
            log_level="info",
            loop="asyncio",
        )
        uvicorn_server = uvicorn.Server(config)
        uvicorn_server.install_signal_handlers = lambda: None

        async def wait_for_ready(server_obj):
            global _full_server_ready
            while not server_obj.started:
                await asyncio.sleep(0.1)
            _full_server_ready = True
            _log("Full FastAPI server READY on port 8001!")

        async def run_uvicorn():
            asyncio.create_task(wait_for_ready(uvicorn_server))
            await uvicorn_server.serve()

        def run_loop():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(run_uvicorn())

        uvicorn_thread = threading.Thread(target=run_loop, daemon=True, name="uvicorn-thread")
        uvicorn_thread.start()

        for i in range(30):
            if _full_server_ready:
                _log("Full server started successfully on port 8001!")
                break
            time.sleep(1)

        if not _full_server_ready:
            _log("Full server did not start within 30s, keeping minimal server only")

    except Exception as e:
        import traceback
        error_msg = f"Full server startup failed: {type(e).__name__}: {e}\n{traceback.format_exc()}"
        _log(error_msg)
        _write_error_log(error_msg)
        _log("Keeping minimal server on port 8000")


def _start_minimal_server(static_dir):
    """Start the minimal stdlib HTTP server on port 8000."""
    global _server, _server_ready

    try:
        _log("Phase 1: Starting minimal stdlib server...")

        class MinimalHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                return

            def _send_json(self, data, status=200):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _send_file(self, filepath):
                if not os.path.isfile(filepath):
                    self.send_error(404)
                    return
                mime, _ = mimetypes.guess_type(filepath)
                if not mime:
                    mime = "application/octet-stream"
                with open(filepath, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)

            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/api/health":
                    mode = "full" if _full_server_ready else "minimal"
                    self._send_json({"status": "ok", "version": "1.0.0", "platform": "android", "mode": mode})
                elif path == "/api/downloads":
                    tasks_list = list(_download_tasks.values())
                    self._send_json(tasks_list)
                elif path == "/api/settings":
                    self._send_json({
                        "download_dir": _get_download_dir(),
                        "max_concurrent": 3,
                        "proxy": None,
                        "output_template": "%(title)s.%(ext)s",
                        "theme": "dark",
                    })
                elif path == "/api/system/drives":
                    drives = []
                    if os.path.exists("/storage/emulated/0"):
                        drives.append("/storage/emulated/0/")
                    self._send_json(drives)
                elif path.startswith("/api/system/directories"):
                    qs = parse_qs(parsed.query)
                    dir_path = qs.get("path", [""])[0]
                    self._handle_dir_list(dir_path)
                elif path == "/api/downloads/cookies/list":
                    self._send_json([])
                elif path == "/api/system/browsers":
                    self._send_json([])
                elif path == "/api/system/ffmpeg":
                    self._send_json({"available": False, "path": None})
                elif path == "/debug":
                    self._handle_debug_page()
                elif path == "/api/system/test-ytdlp":
                    self._handle_test_ytdlp()
                elif path == "/api/system/error-log":
                    self._handle_error_log()
                elif path == "/api/system/status":
                    self._handle_status()
                elif path == "/api/system/test-import":
                    self._handle_test_import()
                elif static_dir and (path.startswith("/assets/") or path in ("/", "")):
                    if path in ("/", ""):
                        filepath = os.path.join(static_dir, "index.html")
                    else:
                        filepath = os.path.join(static_dir, path.lstrip("/"))
                    if os.path.isfile(filepath):
                        self._send_file(filepath)
                    else:
                        filepath = os.path.join(static_dir, "index.html")
                        if os.path.isfile(filepath):
                            self._send_file(filepath)
                        else:
                            self._send_json({"error": "Frontend not found"}, 404)
                elif static_dir:
                    filepath = os.path.join(static_dir, path.lstrip("/"))
                    if os.path.isfile(filepath):
                        self._send_file(filepath)
                    else:
                        filepath = os.path.join(static_dir, "index.html")
                        if os.path.isfile(filepath):
                            self._send_file(filepath)
                        else:
                            self._send_json({"error": "Not found"}, 404)
                else:
                    self._send_json({"error": "No frontend files"}, 404)

            def _handle_dir_list(self, path):
                if not path:
                    items = []
                    if os.path.exists("/storage/emulated/0"):
                        items.append({
                            "name": "Internal Storage",
                            "is_dir": True,
                            "path": "/storage/emulated/0",
                        })
                    self._send_json({"path": "", "children": items})
                    return
                if not os.path.isdir(path):
                    self._send_json({"path": path, "children": [], "error": "Not a directory"})
                    return
                children = []
                try:
                    for name in sorted(os.listdir(path)):
                        full = os.path.join(path, name)
                        if os.path.isdir(full) and not name.startswith("."):
                            children.append({"name": name, "is_dir": True, "path": full})
                except Exception:
                    pass
                self._send_json({"path": path, "children": children})

            def _handle_test_ytdlp(self):
                """Test if yt-dlp can be imported and basic functionality works."""
                result = {"success": False, "steps": []}
                try:
                    result["steps"].append({"step": "start", "status": "ok"})

                    import yt_dlp
                    result["steps"].append({"step": "import_yt_dlp", "status": "ok", "version": yt_dlp.version.__version__})

                    ydl = yt_dlp.YoutubeDL({"quiet": True})
                    result["steps"].append({"step": "create_ydl", "status": "ok"})

                    test_url = "https://www.bilibili.com/video/BV1GJ411x7h7"
                    try:
                        info = ydl.extract_info(test_url, download=False)
                        result["steps"].append({"step": "extract_info", "status": "ok", "title": info.get("title", "Unknown") if info else None})
                    except Exception as e:
                        result["steps"].append({"step": "extract_info", "status": "error", "error": str(e)})

                    download_dir = _get_download_dir()
                    if os.path.exists(download_dir):
                        result["steps"].append({"step": "download_dir", "status": "ok", "path": download_dir})
                    else:
                        try:
                            os.makedirs(download_dir, exist_ok=True)
                            result["steps"].append({"step": "download_dir", "status": "created", "path": download_dir})
                        except Exception as e:
                            result["steps"].append({"step": "download_dir", "status": "error", "error": str(e)})

                    result["success"] = True
                except Exception as e:
                    import traceback
                    result["error"] = str(e)
                    result["traceback"] = traceback.format_exc()

                self._send_json(result)

            def _handle_debug_page(self):
                """Generate an HTML debug page for easy mobile debugging."""
                import threading
                import html as html_module

                sections = []

                sections.append(f"""
                <h2>服务器状态</h2>
                <table>
                <tr><td>最小服务器 (8000)</td><td>{"运行中" if _server_ready else "未启动"}</td></tr>
                <tr><td>完整服务器 FastAPI (8001)</td><td>{"运行中" if _full_server_ready else "未启动"}</td></tr>
                <tr><td>Android 环境</td><td>{_is_android()}</td></tr>
                </table>
                """)

                thread_rows = ""
                for t in threading.enumerate():
                    status = "运行中" if t.is_alive() else "停止"
                    thread_rows += f"<tr><td>{html_module.escape(t.name)}</td><td>{status}</td><td>{'守护' if t.daemon else '主线程'}</td></tr>"
                sections.append(f"""
                <h2>线程 ({threading.active_count()})</h2>
                <table><tr><th>名称</th><th>状态</th><th>类型</th></tr>{thread_rows}</table>
                """)

                task_rows = ""
                for tid, task in _download_tasks.items():
                    err = task.get('error', '')
                    err_display = f'<span style="color:red">{html_module.escape(str(err)[:200])}</span>' if err else ''
                    task_rows += f"""<tr>
                    <td>{html_module.escape(str(task.get('url',''))[:60])}</td>
                    <td>{html_module.escape(str(task.get('status','')))}</td>
                    <td>{task.get('progress_pct', 0)}%</td>
                    <td>{html_module.escape(str(task.get('title',''))[:40])}</td>
                    <td>{err_display}</td>
                    </tr>"""
                if not task_rows:
                    task_rows = "<tr><td colspan='5'>暂无任务</td></tr>"
                sections.append(f"""
                <h2>下载任务 ({len(_download_tasks)})</h2>
                <table><tr><th>URL</th><th>状态</th><th>进度</th><th>标题</th><th>错误</th></tr>{task_rows}</table>
                """)

                log_content = ""
                try:
                    if os.path.exists(_ERROR_LOG_PATH):
                        with open(_ERROR_LOG_PATH, "r", encoding="utf-8") as f:
                            log_content = f.read()
                        if len(log_content) > 10000:
                            log_content = log_content[-10000:]
                except Exception:
                    log_content = "无法读取日志文件"

                sections.append(f"""
                <h2>错误日志</h2>
                <pre style="background:#1a1a1a;color:#0f0;padding:10px;overflow-x:auto;font-size:12px;max-height:500px">{html_module.escape(log_content) if log_content else "日志为空"}</pre>
                """)

                sections.append("""
                <h2>操作</h2>
                <p><a href="/api/system/status" style="color:#4fc3f7">查看完整状态 (JSON)</a> |
                <a href="/api/system/error-log" style="color:#4fc3f7">查看错误日志 (JSON)</a> |
                <a href="/api/system/test-import" style="color:#4fc3f7">测试 FastAPI 导入</a></p>
                <p><button onclick="location.reload()" style="padding:10px 20px;font-size:16px">刷新页面</button></p>
                """)

                html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>视频搬运工 调试</title>
<style>
body {{ font-family: sans-serif; background: #121212; color: #e0e0e0; padding: 10px; }}
h2 {{ color: #4fc3f7; border-bottom: 1px solid #333; padding-bottom: 5px; }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
td, th {{ border: 1px solid #333; padding: 6px 8px; text-align: left; font-size: 13px; }}
th {{ background: #1e1e1e; color: #4fc3f7; }}
tr:nth-child(even) {{ background: #1a1a1a; }}
a {{ text-decoration: none; }}
</style></head><body>
<h1>视频搬运工 调试面板</h1>
{"".join(sections)}
</body></html>"""

                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))

            def _handle_error_log(self):
                """Return the error log contents."""
                try:
                    if os.path.exists(_ERROR_LOG_PATH):
                        with open(_ERROR_LOG_PATH, "r", encoding="utf-8") as f:
                            content = f.read()
                        self._send_json({"exists": True, "content": content, "path": _ERROR_LOG_PATH})
                    else:
                        self._send_json({"exists": False, "content": "", "path": _ERROR_LOG_PATH})
                except Exception as e:
                    self._send_json({"exists": False, "error": str(e)})

            def _handle_status(self):
                """Return server status including active threads and tasks."""
                import threading
                threads = []
                for t in threading.enumerate():
                    threads.append({
                        "name": t.name,
                        "daemon": t.daemon,
                        "alive": t.is_alive(),
                    })

                tasks = []
                for tid, task in _download_tasks.items():
                    tasks.append({
                        "id": tid,
                        "url": task.get("url"),
                        "status": task.get("status"),
                        "progress": task.get("progress_pct"),
                        "title": task.get("title"),
                        "error": task.get("error"),
                    })

                self._send_json({
                    "server_ready": _server_ready,
                    "full_server_ready": _full_server_ready,
                    "static_dir": static_dir if 'static_dir' in dir() else None,
                    "is_android": _is_android(),
                    "threads": threads,
                    "tasks": tasks,
                    "task_count": len(_download_tasks),
                })

            def _handle_test_import(self):
                """Test if app.main can be imported - diagnostic for FastAPI startup issues."""
                result = {"success": False, "steps": []}
                try:
                    result["steps"].append({"step": "start", "status": "ok"})

                    import fastapi
                    result["steps"].append({"step": "fastapi", "version": fastapi.__version__})

                    import uvicorn
                    result["steps"].append({"step": "uvicorn", "version": uvicorn.__version__})

                    import pydantic
                    result["steps"].append({"step": "pydantic", "version": pydantic.VERSION})

                    from app.main import app as fastapi_app
                    result["steps"].append({"step": "app_main", "status": "ok"})

                    routes = [r.path for r in fastapi_app.routes if hasattr(r, 'path')]
                    result["steps"].append({"step": "routes", "count": len(routes), "paths": routes[:20]})

                    result["success"] = True
                    result["full_server_ready"] = _full_server_ready
                except Exception as e:
                    import traceback
                    result["error"] = str(e)
                    result["traceback"] = traceback.format_exc()
                self._send_json(result)

            def do_POST(self):
                parsed = urlparse(self.path)
                path = parsed.path
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length) if content_length > 0 else b""

                if path == "/api/downloads":
                    try:
                        data = json.loads(body) if body else {}
                        urls = data.get("urls", [])

                        download_dir = _get_download_dir()
                        _log(f"Using download_dir: {download_dir}")

                        os.makedirs(download_dir, exist_ok=True)

                        task_ids = []
                        for url in urls:
                            clean_url = _extract_url(url)
                            _log(f"URL extracted: '{url}' -> '{clean_url}'")

                            global _task_counter
                            _task_counter += 1
                            task_id = str(_task_counter)

                            _download_tasks[task_id] = {
                                "id": task_id,
                                "url": clean_url,
                                "status": "queued",
                                "title": "",
                                "thumbnail": None,
                                "progress_pct": 0.0,
                                "speed": None,
                                "eta": None,
                                "filename": None,
                                "filesize": None,
                                "error": None,
                                "created_at": time.time(),
                                "completed_at": None,
                            }

                            thread = threading.Thread(
                                target=_run_ytdlp_download,
                                args=(task_id, clean_url, download_dir),
                                daemon=True
                            )
                            thread.start()

                            task_ids.append(task_id)
                            _log(f"Created download task {task_id} for {clean_url}")

                        self._send_json({"task_ids": task_ids})
                    except Exception as e:
                        self._send_json({"error": str(e)}, 500)
                elif path == "/api/downloads/info":
                    self._send_json({"error": "Info extraction not available in minimal mode"}, 501)
                elif path.startswith("/api/downloads/cookies/upload"):
                    self._send_json({"message": "Cookie upload not available in minimal mode"})
                elif path == "/api/downloads/cookies/auto":
                    self._send_json({"error": "Auto cookie not available on Android"}, 501)
                else:
                    self._send_json({"error": "Not found"}, 404)

            def do_PUT(self):
                parsed = urlparse(self.path)
                if parsed.path == "/api/settings":
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length) if content_length > 0 else b""
                    try:
                        data = json.loads(body) if body else {}
                        self._send_json(data)
                    except Exception:
                        self._send_json({"error": "Invalid JSON"}, 400)
                else:
                    self._send_json({"error": "Not found"}, 404)

            def do_DELETE(self):
                self._send_json({"cancelled": False, "message": "Minimal mode"})

        class ReusableHTTPServer(HTTPServer):
            allow_reuse_address = True

        server = ReusableHTTPServer(("127.0.0.1", 8000), MinimalHandler)
        _server = server
        _server_ready = True
        _log("Minimal server READY on port 8000!")

        serve_thread = threading.Thread(target=server.serve_forever, daemon=True)
        serve_thread.start()

    except Exception as e:
        error_msg = f"Minimal server failed: {type(e).__name__}: {e}"
        _startup_error = error_msg
        _log(error_msg)
        _write_error_log(error_msg)


def stop():
    global _server
    if _server:
        try:
            if hasattr(_server, "shutdown"):
                _server.shutdown()
        except Exception:
            pass

