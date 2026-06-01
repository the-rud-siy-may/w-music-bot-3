"""
Helper utilities.
"""

from __future__ import annotations

import hashlib
import re
import time
import unicodedata
from datetime import datetime
from typing import Any


def normalize_username(username: str) -> str:
    return username.strip().lower()


def normalize_display_name(name: str) -> str:
    if not name:
        return ""
    lowered = unicodedata.normalize("NFKC", name).strip().lower()
    return re.sub(r"[^\w]", "", lowered, flags=re.UNICODE)


def display_names_match(configured: str, display: str) -> bool:
    a = normalize_display_name(configured)
    b = normalize_display_name(display)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 3 and shorter in longer


def is_url(text: str) -> bool:
    return bool(re.match(r"https?://\S+", text.strip(), re.IGNORECASE))


def truncate(text: str, max_len: int = 120, suffix: str = "…") -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def message_fingerprint(username: str, message: str, timestamp: datetime | float | str) -> str:
    if isinstance(timestamp, datetime):
        ts = timestamp.isoformat()
    elif isinstance(timestamp, float):
        ts = str(int(timestamp))
    else:
        ts = str(timestamp)
    payload = f"{normalize_username(username)}|{message.strip()}|{ts}"
    return hashlib.sha256(payload.encode()).hexdigest()


def normalize_command_text(text: str) -> str:
    body = text.strip().lower()
    return re.sub(r"\s+", " ", body)


def command_fingerprint(username: str, raw_text: str, timestamp: float | None = None) -> str:
    ts = timestamp if timestamp is not None else time.time()
    payload = f"{normalize_username(username)}|{normalize_command_text(raw_text)}|{int(ts)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def safe_int(value: str, default: int | None = None) -> int | None:
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return default


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "unknown"
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


def deep_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key, default)
        if current is default:
            return default
    return current
