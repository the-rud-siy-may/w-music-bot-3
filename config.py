"""
Central configuration for the Wakie music assistant bot.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
STORAGE_DIR = PROJECT_ROOT / "storage"

try:
    from dotenv import load_dotenv

    for _env_path in (PROJECT_ROOT / ".env", STORAGE_DIR / ".env"):
        if _env_path.is_file():
            load_dotenv(_env_path, override=False)
except ImportError:
    pass

CACHE_DIR = STORAGE_DIR / "cache"
STATE_FILE = STORAGE_DIR / "state.json"
QUEUE_FILE = STORAGE_DIR / "queue.json"
DEFAULT_PLAYLIST_FILE = STORAGE_DIR / "default_playlist.json"
LOG_DIR = PROJECT_ROOT / "logs"
SONGS_DIR = PROJECT_ROOT / "songs"

LDPLAYER_SERIAL: str = os.getenv("WAKIE_ADB_SERIAL", "emulator-5554")
LDPLAYER_PACKAGE: str = os.getenv("WAKIE_PACKAGE", "com.wakie.android")

VLC_AUDIO_DEVICE: str = os.getenv("VLC_AUDIO_DEVICE", "CABLE Input (VB-Audio Virtual Cable)")
DEFAULT_VOLUME: int = int(os.getenv("WAKIE_DEFAULT_VOLUME", "80"))
MAX_VOLUME: int = 200

OWNER_USERNAME: str = os.getenv("WAKIE_OWNER", "owner")
BOT_USERNAME: str = os.getenv("WAKIE_BOT_USERNAME", os.getenv("WAKIE_OWNER", ""))

MESSAGE_POLL_INTERVAL: float = float(os.getenv("WAKIE_POLL_INTERVAL", "1.5"))
COMMAND_COOLDOWN_SECONDS: float = float(os.getenv("WAKIE_CMD_COOLDOWN", "2.0"))
MAX_PROCESSED_COMMAND_CACHE: int = 500

READER_RETRY_ATTEMPTS: int = int(os.getenv("WAKIE_READER_RETRIES", "3"))
READER_RETRY_DELAY: float = float(os.getenv("WAKIE_READER_RETRY_DELAY", "1.0"))
READER_OCR_ENABLED: bool = os.getenv("WAKIE_OCR_ENABLED", "false").lower() in ("1", "true", "yes")
READER_OCR_LANGUAGES: list[str] = [
    lang.strip() for lang in os.getenv("WAKIE_OCR_LANGS", "en").split(",") if lang.strip()
]
READER_MAX_SEEN_CACHE: int = int(os.getenv("WAKIE_MAX_SEEN_MESSAGES", "1000"))
READER_CONNECT_TIMEOUT: int = int(os.getenv("WAKIE_CONNECT_TIMEOUT", "30"))

SEND_RETRY_ATTEMPTS: int = int(os.getenv("WAKIE_SEND_RETRIES", "3"))
SEND_POST_TYPE_DELAY: float = float(os.getenv("WAKIE_SEND_TYPE_DELAY", "0.45"))

DOWNLOAD_FORMAT: str = os.getenv("YTDLP_FORMAT", "bestaudio/best")
DOWNLOAD_TIMEOUT: int = int(os.getenv("YTDLP_TIMEOUT", "120"))

PLAYBACK_MAX_RETRIES: int = int(os.getenv("WAKIE_PLAYBACK_RETRIES", "3"))
PLAYBACK_RETRY_DELAY: float = float(os.getenv("WAKIE_PLAYBACK_RETRY_DELAY", "2.0"))
PLAYBACK_BUFFER_TIMEOUT: float = float(os.getenv("WAKIE_BUFFER_TIMEOUT", "15.0"))
YTDLP_TIMEOUT: int = int(os.getenv("YTDLP_TIMEOUT", "120"))

SAFE_SEND_ONLY: bool = os.getenv("WAKIE_SAFE_SEND", "true").lower() in ("1", "true", "yes")
USE_LOCAL_AUTOPLAY: bool = os.getenv("WAKIE_LOCAL_AUTOPLAY", "true").lower() in ("1", "true", "yes")
UNKNOWN_CMD_COOLDOWN: float = float(os.getenv("WAKIE_UNKNOWN_COOLDOWN", "30"))
MAX_TRACK_DURATION_SECONDS: int = int(os.getenv("WAKIE_MAX_TRACK_DURATION", str(15 * 60)))


def _parse_delegated_users() -> list[str]:
    raw = os.getenv("WAKIE_DELEGATED", "")
    if not raw.strip():
        return []
    return [u.strip().lower() for u in raw.split(",") if u.strip()]


@dataclass
class BotConfig:
    project_root: Path = PROJECT_ROOT
    storage_dir: Path = STORAGE_DIR
    cache_dir: Path = CACHE_DIR
    state_file: Path = STATE_FILE
    queue_file: Path = QUEUE_FILE
    default_playlist_file: Path = DEFAULT_PLAYLIST_FILE
    log_dir: Path = LOG_DIR
    songs_dir: Path = SONGS_DIR

    adb_serial: str = LDPLAYER_SERIAL
    wakie_package: str = LDPLAYER_PACKAGE

    vlc_audio_device: str = VLC_AUDIO_DEVICE
    default_volume: int = DEFAULT_VOLUME
    max_volume: int = MAX_VOLUME

    owner_username: str = OWNER_USERNAME.lower()
    bot_username: str = BOT_USERNAME.strip()
    delegated_users: list[str] = field(default_factory=_parse_delegated_users)

    poll_interval: float = MESSAGE_POLL_INTERVAL
    command_cooldown: float = COMMAND_COOLDOWN_SECONDS
    max_processed_cache: int = MAX_PROCESSED_COMMAND_CACHE

    reader_retry_attempts: int = READER_RETRY_ATTEMPTS
    reader_retry_delay: float = READER_RETRY_DELAY
    reader_ocr_enabled: bool = READER_OCR_ENABLED
    reader_ocr_languages: list[str] = field(default_factory=lambda: list(READER_OCR_LANGUAGES))
    reader_max_seen_cache: int = READER_MAX_SEEN_CACHE
    reader_connect_timeout: int = READER_CONNECT_TIMEOUT

    send_retry_attempts: int = SEND_RETRY_ATTEMPTS
    send_post_type_delay: float = SEND_POST_TYPE_DELAY

    download_format: str = DOWNLOAD_FORMAT
    download_timeout: int = DOWNLOAD_TIMEOUT
    ytdlp_timeout: int = YTDLP_TIMEOUT

    playback_max_retries: int = PLAYBACK_MAX_RETRIES
    playback_retry_delay: float = PLAYBACK_RETRY_DELAY
    playback_buffer_timeout: float = PLAYBACK_BUFFER_TIMEOUT

    safe_send_only: bool = SAFE_SEND_ONLY
    use_local_autoplay: bool = USE_LOCAL_AUTOPLAY
    unknown_cmd_cooldown: float = UNKNOWN_CMD_COOLDOWN
    max_track_duration_seconds: int = MAX_TRACK_DURATION_SECONDS

    locked: bool = False
    muted: bool = False

    def ensure_dirs(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.songs_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> BotConfig:
    cfg = BotConfig()
    cfg.ensure_dirs()
    return cfg
