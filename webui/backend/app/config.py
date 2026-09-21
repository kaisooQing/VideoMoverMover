"""Application settings with JSON file persistence."""
from __future__ import annotations
import json
import os
from pathlib import Path
from .models import Settings


def _settings_dir() -> Path:
    """Get the settings directory (APPDATA or exe location)."""
    if getattr(os.sys, 'frozen', False):
        return Path(os.sys.executable).parent / 'config'
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
    path.write_text(settings.model_dump_json(indent=2), encoding='utf-8')


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
    data = settings.model_dump()
    data.update({k: v for k, v in updates.items() if v is not None})
    _settings = Settings(**data)
    save_settings(_settings)
    return _settings
