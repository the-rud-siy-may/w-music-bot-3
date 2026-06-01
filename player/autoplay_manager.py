"""
Default autoplay playlist — fills the queue when user requests are empty.
"""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path
from typing import TYPE_CHECKING

from player.models import QueueEntry
from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig
    from player.youtube_service import YouTubeService

logger = get_logger(__name__)


class AutoplayManager:
    """
    Manages 24/7 autoplay from storage/default_playlist.json.

    User queue takes priority — autoplay pauses while user items exist.
    Reshuffles playlist after a full pass.
    """

    def __init__(self, config: BotConfig, youtube: YouTubeService) -> None:
        self._config = config
        self._youtube = youtube
        self._playlist_path = config.default_playlist_file
        self._urls: list[str] = []
        self._order: list[str] = []
        self._index = 0
        self._paused_for_user = False
        self._active = False
        self._lock = asyncio.Lock()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def paused_for_user(self) -> bool:
        return self._paused_for_user

    async def load(self) -> None:
        """Load playlist URLs from JSON."""
        async with self._lock:
            self._urls = self._read_playlist_file()
            self._reshuffle()
        logger.info("Autoplay playlist loaded: %d track(s)", len(self._urls))

    def pause_for_user(self) -> None:
        """User added a song — autoplay yields until user queue drains."""
        if not self._paused_for_user:
            logger.info("Autoplay paused — user queue active")
        self._paused_for_user = True
        self._active = False

    def resume_if_allowed(self) -> bool:
        """Resume autoplay when user queue is empty."""
        if not self._paused_for_user:
            return False
        self._paused_for_user = False
        logger.info("Autoplay resumed — user queue empty")
        return True

    async def next_entry(self) -> QueueEntry | None:
        """
        Build the next autoplay QueueEntry (extracts stream URL).

        Returns None if autoplay is paused or playlist is empty.
        """
        if self._paused_for_user:
            return None

        async with self._lock:
            if not self._order:
                self._urls = self._read_playlist_file()
                if not self._urls:
                    return None
                self._reshuffle()

            if self._index >= len(self._order):
                logger.info("Autoplay playlist complete — reshuffling")
                self._reshuffle()

            url = self._order[self._index]
            self._index += 1

        try:
            info = await self._youtube.extract_stream(url)
            self._active = True
            return QueueEntry.from_stream_info(info, requested_by="autoplay", source="autoplay")
        except Exception as exc:
            logger.error("Autoplay extract failed for %s: %s", url, exc)
            return None

    def _read_playlist_file(self) -> list[str]:
        path = Path(self._playlist_path)
        if not path.is_file():
            logger.warning("Default playlist not found: %s", path)
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(u).strip() for u in data if str(u).strip()]
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read playlist: %s", exc)
        return []

    def _reshuffle(self) -> None:
        self._order = list(self._urls)
        random.shuffle(self._order)
        self._index = 0
        logger.debug("Autoplay order reshuffled (%d tracks)", len(self._order))
