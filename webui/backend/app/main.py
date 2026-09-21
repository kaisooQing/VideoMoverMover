"""FastAPI application entry point."""
from __future__ import annotations
import asyncio
import logging
import os
import sys
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .download_manager import download_manager
from .websocket import ws_manager
from .routers import downloads, settings, system

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Ensure yt_dlp is importable (skip in frozen mode - yt-dlp is bundled)
if not getattr(sys, 'frozen', False):
    _ytdlp_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    if _ytdlp_root not in sys.path:
        sys.path.insert(0, _ytdlp_root)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    loop = asyncio.get_event_loop()
    download_manager.set_loop(loop)
    download_manager.set_broadcast(ws_manager.send_progress)

    # Start the WebSocket broadcast background task
    broadcast_task = asyncio.create_task(ws_manager.broadcast_loop())
    logger.info("yt-dlp WebUI started on http://localhost:8000")

    # Open browser in production mode (not during dev with Vite)
    if not os.environ.get('YTDL_WEBUI_DEV'):
        try:
            webbrowser.open('http://localhost:8000')
        except Exception:
            pass

    yield

    broadcast_task.cancel()
    logger.info("yt-dlp WebUI stopped")


app = FastAPI(
    title="yt-dlp WebUI",
    description="Web interface for yt-dlp video downloader",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for development (Vite dev server on port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(downloads.router)
app.include_router(settings.router)
app.include_router(system.router)


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """WebSocket endpoint for real-time download progress."""
    await ws_manager.connect(websocket)
    await ws_manager.handle_client(websocket)


# Serve Vue frontend static files in production mode
def _get_static_dir() -> Path | None:
    """Find the built Vue frontend directory."""
    # When frozen as EXE: bundled in sys._MEIPASS/static
    if getattr(sys, 'frozen', False):
        meipass = Path(sys._MEIPASS)
        static = meipass / 'static'
        if static.is_dir():
            return static

    # Development: look for frontend/dist relative to this file
    dev_dist = Path(__file__).parent.parent.parent / 'frontend' / 'dist'
    if dev_dist.is_dir():
        return dev_dist

    return None


static_dir = _get_static_dir()
if static_dir:
    app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the Vue SPA for all non-API routes."""
        # Try to serve the exact file first
        file_path = static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        # Fall back to index.html for SPA routing
        index = static_dir / "index.html"
        if index.is_file():
            return FileResponse(str(index))
        return {"detail": "Not found"}, 404


def run():
    """Entry point for running the server."""
    import uvicorn
    port = int(os.environ.get('YTDL_WEBUI_PORT', '8000'))
    # Pass app object directly — string ref fails in PyInstaller frozen mode
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


def launch():
    """PyInstaller entry point."""
    run()


if __name__ == "__main__":
    run()
