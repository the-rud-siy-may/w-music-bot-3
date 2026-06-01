"""
Media downloader using yt-dlp.

Resolves queries/URLs to local audio files in storage/cache/.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig

logger = get_logger(__name__)


class Downloader:
    """
    Async wrapper around yt-dlp for fetching audio.

    Placeholder: subprocess / thread-pool invocation of yt-dlp will be
    added when download pipeline is implemented.
    """

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._cache_dir: Path = config.cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Downloader cache → %s", self._cache_dir)

    async def resolve(self, query: str) -> tuple[str, Path | None]:
        """
        Resolve a query or URL to (title, local_file_path).

        Placeholder returns query as title with no file.
        """
        logger.info("Resolve (placeholder): %s", query[:80])
        await asyncio.sleep(0)  # yield control
        return query, None

    async def download(self, query: str) -> Path | None:
        """
        Download audio to cache and return the file path.

        Placeholder — not yet implemented.
        """
        logger.info("Download (placeholder): %s", query[:80])
        return None

    async def clear_cache(self) -> int:
        """Delete all files in cache/; return count removed."""
        count = 0
        try:
            for path in self._cache_dir.iterdir():
                if path.is_file():
                    path.unlink()
                    count += 1
            logger.info("Cache cleared: %d file(s)", count)
        except OSError as exc:
            logger.error("Cache clear failed: %s", exc)
        return count
