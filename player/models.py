"""
Shared queue / stream data models.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class QueueEntry:
    """A queued or currently playing track (local file or YouTube stream)."""

    id: str
    title: str
    youtube_url: str = ""
    stream_url: str = ""
    requested_by: str = ""
    duration: float = 0
    query: str = ""
    source: str = "user"  # user | autoplay
    file_path: str | None = None
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(
        cls,
        *,
        title: str,
        youtube_url: str = "",
        stream_url: str = "",
        requested_by: str = "",
        duration: float = 0,
        query: str = "",
        source: str = "user",
        file_path: str | None = None,
    ) -> QueueEntry:
        return cls(
            id=str(uuid.uuid4())[:8],
            title=title,
            youtube_url=youtube_url,
            stream_url=stream_url,
            requested_by=requested_by,
            duration=float(duration or 0),
            query=query or title,
            source=source,
            file_path=file_path,
        )

    @classmethod
    def from_stream_info(cls, info: dict[str, Any], *, requested_by: str = "", source: str = "user") -> QueueEntry:
        return cls.create(
            title=info.get("title") or "Unknown",
            youtube_url=info.get("youtube_url") or "",
            stream_url=info.get("stream_url") or "",
            requested_by=requested_by,
            duration=float(info.get("duration") or 0),
            query=info.get("query") or info.get("title") or "",
            source=source,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "youtube_url": self.youtube_url,
            "stream_url": self.stream_url,
            "requested_by": self.requested_by,
            "duration": self.duration,
        }

    def playable_url(self) -> str | None:
        """Return the URL/path VLC should open."""
        if self.stream_url:
            return self.stream_url
        if self.file_path:
            return self.file_path
        return None

    def update_stream(self, info: dict[str, Any]) -> None:
        """Refresh stream URL metadata after yt-dlp re-extract."""
        if info.get("stream_url"):
            self.stream_url = info["stream_url"]
        if info.get("title"):
            self.title = info["title"]
        if info.get("duration"):
            self.duration = float(info["duration"])
        if info.get("youtube_url"):
            self.youtube_url = info["youtube_url"]
