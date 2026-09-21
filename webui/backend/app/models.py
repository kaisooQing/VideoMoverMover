"""Pydantic models for API request/response schemas."""
from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class DownloadStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FormatOption(BaseModel):
    """Video format selection preset."""
    mode: str = "best"  # best, worst, audio_only, custom
    format_string: Optional[str] = None  # yt-dlp format string for custom mode
    resolution: Optional[str] = None  # e.g. "1080p", "720p"


class SubtitleOptions(BaseModel):
    """Subtitle download options."""
    enabled: bool = False
    languages: str = "zh-Hans,en"  # comma-separated language codes
    auto_subs: bool = True  # download auto-generated subtitles
    sub_format: str = "srt"  # srt, vtt, ass, lrc
    embed_subs: bool = False  # embed subtitles into video file


class MetadataOverrides(BaseModel):
    """Optional metadata overrides for the output file."""
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    upload_date: Optional[str] = None


class DownloadRequest(BaseModel):
    """Request body for creating a download task."""
    urls: list[str] = Field(..., min_length=1, description="One or more video URLs")
    download_dir: Optional[str] = Field(None, description="Custom download directory")
    format_option: FormatOption = Field(default_factory=FormatOption)
    cookie_browser: Optional[str] = Field(None, description="Browser name for cookie extraction")
    cookie_file: Optional[str] = Field(None, description="Path to cookies.txt file")
    proxy: Optional[str] = Field(None, description="HTTP/SOCKS proxy URL")
    subtitle_options: SubtitleOptions = Field(default_factory=SubtitleOptions)
    output_template: str = Field("%(title)s.%(ext)s", description="yt-dlp output template")
    metadata: Optional[MetadataOverrides] = None
    write_thumbnail: bool = False
    embed_thumbnail: bool = False
    embed_metadata: bool = True
    extra_args: Optional[list[str]] = Field(None, description="Additional yt-dlp CLI args")


class DownloadTaskInfo(BaseModel):
    """Status info for a download task."""
    id: str
    url: str
    status: DownloadStatus = DownloadStatus.QUEUED
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    progress_pct: float = 0.0
    speed: Optional[str] = None
    eta: Optional[str] = None
    filename: Optional[str] = None
    filesize: Optional[str] = None
    error: Optional[str] = None
    created_at: float = 0.0
    completed_at: Optional[float] = None


class Settings(BaseModel):
    """Persisted application settings."""
    download_dir: str = Field(default=str(Path.home() / "Downloads" / "yt-dlp"), description="Default download directory")
    max_concurrent: int = Field(default=3, ge=1, le=10)
    proxy: Optional[str] = None
    cookie_browser: Optional[str] = None
    output_template: str = "%(title)s.%(ext)s"
    ffmpeg_path: Optional[str] = None
    embed_metadata: bool = True
    embed_thumbnail: bool = False
    write_subs: bool = False
    sub_languages: str = "zh-Hans,en"
    theme: str = "light"


class VideoInfo(BaseModel):
    """Extracted video info for preview."""
    id: str
    title: str
    thumbnail: Optional[str] = None
    duration: Optional[float] = None
    uploader: Optional[str] = None
    description: Optional[str] = None
    formats: list[dict] = Field(default_factory=list)
    subtitles: dict = Field(default_factory=dict)
