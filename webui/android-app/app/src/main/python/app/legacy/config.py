"""Application settings with JSON file persistence - Android adapted."""
from __future__ import annotations
import json
import os
from pathlib import Path
from .models import Settings


def _settings_dir() -> Path:
    """Get the settings directory for Android."""
    # Try Android-specific path first
    try:
        from com.chaquo.python import Python
        context = Python.getPlatform().getApplication()
        files_dir = context.getFilesDir().getAbsolutePath()
        return Path(files_dir) / 'config'
    except Exception:
        pass
    
    # Fallback for testing on other platforms
    if getattr(os.sys, 'frozen', False):
        return Path(os.sys.executable).parent / 'config'
    
    # Android fallback
    if 'ANDROID_ROOT' in os.environ:
        return Path('/data/data/com.ytdlp.webui/files/config')
    
    appdata = os.environ.get('APPDATA')
    if appdata:
        return Path(appdata) / 'yt-dlp-webui'
    
    return Path(__file__).parent.parent / 'config'


def _settings_path() -> Path:
    return _settings_dir() / 'settings.json'


def load_settings() -> Settings:
    """Load settings from JSON file, return defaults if not found."""
    path = _settings_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
            return Settings(**data)
        except Exception:
            return Settings()
    return Settings()


def save_settings(settings: Settings) -> None:
    """Save settings to JSON file."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # pydantic v1 uses .json() instead of .model_dump_json()
    path.write_text(settings.json(indent=2), encoding='utf-8')


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def update_settings(updates: dict) -> Settings:
    global _settings
    settings = get_settings()
    # pydantic v1 uses .dict() instead of .model_dump()
    data = settings.dict()
    data.update({k: v for k, v in updates.items() if v is not None})
    _settings = Settings(**data)
    save_settings(_settings)
    return _settings
