"""
YouTube search and stream URL extraction via yt-dlp (no downloads).
"""

from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

import yt_dlp

from utils.helpers import is_url
from utils.logger import get_logger

if TYPE_CHECKING:
    from player.models import QueueEntry

logger = get_logger(__name__)

YTDLP_BASE_OPTS: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "format": "bestaudio/best",
    "noplaylist": True,
    "socket_timeout": 30,
    "retries": 3,
    "fragment_retries": 3,
}


class YouTubeService:
    """Async-safe wrapper around yt-dlp for streaming extraction."""

    def __init__(self, timeout: int = 120) -> None:
        self._timeout = float(timeout)

    async def search_youtube(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Search YouTube and return stream metadata dicts (no download).

        Each dict: title, youtube_url, stream_url, duration, query
        """
        search_url = f"ytsearch{limit}:{query}"
        logger.info("YouTube search: %s", query)

        def _run() -> list[dict[str, Any]]:
            opts = {**YTDLP_BASE_OPTS, "extract_flat": True, "noplaylist": False}
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(search_url, download=False)
            entries = result.get("entries") or []
            return [
                {
                    "title": e.get("title") or "Unknown",
                    "youtube_url": e.get("url") or e.get("webpage_url") or "",
                    "stream_url": "",
                    "duration": float(e.get("duration") or 0),
                    "query": query,
                }
                for e in entries
                if e
            ]

        try:
            return await asyncio.wait_for(asyncio.to_thread(_run), timeout=self._timeout)
        except Exception as exc:
            logger.error("YouTube search failed: %s", exc, exc_info=True)
            return []

    async def extract_stream(self, url_or_query: str) -> dict[str, Any]:
        """
        Resolve a YouTube URL or search query to a streamable audio URL.

        Does NOT download — returns direct stream URL for VLC.
        """
        target = url_or_query.strip()
        if not is_url(target):
            target = f"ytsearch1:{target}"

        logger.info("Extracting stream: %s", url_or_query[:80])

        def _run() -> dict[str, Any]:
            with yt_dlp.YoutubeDL(YTDLP_BASE_OPTS) as ydl:
                info = ydl.extract_info(target, download=False)

            # ytsearch returns a playlist wrapper
            if info.get("_type") == "playlist" and info.get("entries"):
                info = info["entries"][0]

            stream_url = _pick_stream_url(info)
            if not stream_url:
                raise RuntimeError(f"No audio stream URL for: {url_or_query}")

            youtube_url = info.get("webpage_url") or info.get("original_url") or target
            if youtube_url.startswith("ytsearch"):
                youtube_url = info.get("webpage_url") or ""

            return {
                "title": info.get("title") or url_or_query,
                "youtube_url": youtube_url,
                "stream_url": stream_url,
                "duration": float(info.get("duration") or 0),
                "query": url_or_query,
            }

        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=self._timeout)

    async def refresh_stream(self, song: QueueEntry) -> QueueEntry:
        """Re-extract stream URL when the previous one expired."""
        source = song.youtube_url or song.query
        if not source:
            raise RuntimeError(f"Cannot refresh stream without URL: {song.title}")

        logger.info("Refreshing expired stream: %s", song.title)
        info = await self.extract_stream(source)
        song.update_stream(info)
        return song


def _pick_stream_url(info: dict[str, Any]) -> str | None:
    """Select the best direct audio URL from yt-dlp info dict."""
    url = info.get("url")
    if url and isinstance(url, str):
        return url

    formats = info.get("formats") or []
    audio_formats = [
        f for f in formats
        if f.get("url") and f.get("acodec") not in (None, "none")
    ]
    if not audio_formats:
        return None

    # Prefer pure audio, then highest abr
    audio_only = [f for f in audio_formats if f.get("vcodec") in (None, "none")]
    candidates = audio_only or audio_formats
    candidates.sort(key=lambda f: float(f.get("abr") or 0), reverse=True)
    return candidates[0].get("url")
