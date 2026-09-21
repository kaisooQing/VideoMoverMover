"""Startup script for yt-dlp WebUI."""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
YTDLP_DIR = os.path.dirname(HERE)
BACKEND_DIR = os.path.join(HERE, 'backend')
FRONTEND_DIR = os.path.join(HERE, 'frontend')


def start_dev():
    """Start in development mode with hot reload."""
    print("Starting yt-dlp WebUI in DEVELOPMENT mode...")
    print(f"  Backend:  http://localhost:8000")
    print(f"  Frontend: http://localhost:5173")
    print()

    env = os.environ.copy()
    env['PYTHONPATH'] = YTDLP_DIR + os.pathsep + env.get('PYTHONPATH', '')
    env['YTDL_WEBUI_DEV'] = '1'

    # Start backend
    backend = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--reload'],
        cwd=BACKEND_DIR,
        env=env,
    )

    # Start frontend dev server
    frontend = subprocess.Popen(
        ['npm', 'run', 'dev'],
        cwd=FRONTEND_DIR,
    )

    try:
        backend.wait()
    except KeyboardInterrupt:
        backend.terminate()
        frontend.terminate()
        print("\nStopped.")


def start_prod():
    """Start in production mode (serve built frontend)."""
    import uvicorn
    print("Starting yt-dlp WebUI in PRODUCTION mode...")
    print(f"  Open: http://localhost:8000")
    print()

    # Ensure yt_dlp is importable
    sys.path.insert(0, YTDLP_DIR)
    sys.path.insert(0, BACKEND_DIR)

    from app.main import app

    uvicorn.run(app, host='127.0.0.1', port=8000, log_level='info')


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'prod'
    if mode == 'dev':
        start_dev()
    else:
        start_prod()
