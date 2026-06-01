"""
Local-file autoplay — loops songs from songs/ when the user queue is empty.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import TYPE_CHECKING

from player.local_library import AUDIO_EXTENSIONS, list_available_songs
from player.models import QueueEntry
from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig

logger = get_logger(__name__)


class LocalAutoplayManager:
    """Shuffle and loop local audio files from config.songs_dir."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._paths: list[Path] = []
        self._order: list[Path] = []
        self._index = 0
        self._paused_for_user = False
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def paused_for_user(self) -> bool:
        return self._paused_for_user

    async def load(self) -> None:
        self._paths = self._scan_songs()
        self._reshuffle()
        logger.info("Local autoplay loaded: %d song(s) from %s", len(self._paths), self._config.songs_dir)

    def pause_for_user(self) -> None:
        if not self._paused_for_user:
            logger.info("Autoplay paused — user queue active")
        self._paused_for_user = True
        self._active = False

    def resume_if_allowed(self) -> bool:
        if not self._paused_for_user:
            return False
        self._paused_for_user = False
        logger.info("Autoplay resumed — user queue empty")
        return True

    async def next_entry(self) -> QueueEntry | None:
        if self._paused_for_user:
            return None

        if not self._paths:
            self._paths = self._scan_songs()
            if not self._paths:
                logger.warning("No local songs in %s for autoplay", self._config.songs_dir)
                return None
            self._reshuffle()

        if self._index >= len(self._order):
            logger.info("Local autoplay cycle complete — reshuffling")
            self._reshuffle()

        path = self._order[self._index]
        self._index += 1
        self._active = True

        return QueueEntry.create(
            title=path.stem.replace("_", " ").title(),
            file_path=str(path),
            requested_by="autoplay",
            source="autoplay",
            query=path.stem,
        )

    def _scan_songs(self) -> list[Path]:
        songs_dir = Path(self._config.songs_dir)
        if not songs_dir.is_dir():
            return []
        return sorted(
            p.resolve()
            for p in songs_dir.iterdir()
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        )

    def _reshuffle(self) -> None:
        self._order = list(self._paths)
        random.shuffle(self._order)
        self._index = 0
