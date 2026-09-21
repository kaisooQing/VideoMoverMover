"""Entry point for the standalone EXE."""
import os, sys, threading, webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    port = int(os.environ.get('YTDL_WEBUI_PORT', '8000'))
    url = f'http://localhost:{port}'
    print(f'yt-dlp WebUI starting on {url}')
    def _open_browser():
        import time; time.sleep(1.5)
        try: webbrowser.open(url)
        except Exception: pass
    threading.Thread(target=_open_browser, daemon=True).start()
    from app.main import app
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=port, log_level='info')

if __name__ == '__main__':
    main()
