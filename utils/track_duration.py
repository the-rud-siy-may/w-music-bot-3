"""
Track length limits for user-requested songs.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_MAX_DURATION_SECONDS = 15 * 60  # 15 minutes


def format_duration(seconds: float) -> str:
    """Format seconds as M:SS or H:MM:SS."""
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def duration_too_long(duration: float, max_seconds: float) -> bool:
    """True if duration is known and exceeds the limit."""
    return duration > 0 and duration > max_seconds


def reject_message(duration: float, max_seconds: float) -> str:
    max_label = format_duration(max_seconds)
    got_label = format_duration(duration)
    return f"Song is too long ({got_label}). Maximum length is {max_label}."


def check_stream_info(info: dict[str, Any], max_seconds: float) -> str | None:
    """
    Validate yt-dlp stream metadata duration.

    Returns an error message if over limit, else None.
    """
    duration = float(info.get("duration") or 0)
    if duration_too_long(duration, max_seconds):
        return reject_message(duration, max_seconds)
    return None


def get_local_file_duration(path: Path | str) -> float | None:
    """Read audio file length in seconds via VLC (already a project dependency)."""
    path = Path(path)
    if not path.is_file():
        return None

    try:
        import vlc

        instance = vlc.Instance("--quiet")
        media = instance.media_new(str(path.resolve()))
        media.parse()

        for _ in range(30):
            ms = media.get_duration()
            if ms and ms > 0:
                return ms / 1000.0
            time.sleep(0.1)
    except Exception as exc:
        logger.debug("Could not read duration for %s: %s", path, exc)

    return None


def check_local_file(path: Path | str, max_seconds: float) -> str | None:
    """Return error message if local file exceeds max duration."""
    duration = get_local_file_duration(path)
    if duration is None:
        return None
    if duration_too_long(duration, max_seconds):
        return reject_message(duration, max_seconds)
    return None
