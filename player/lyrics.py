"""
Lyrics fetching and live lyrics streaming.

Placeholder for external lyrics API integration and timed chat posting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig

logger = get_logger(__name__)


class LyricsService:
    """Fetch and optionally stream lyrics into Wakie chat."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._live_active = False
        logger.debug("LyricsService initialized (placeholder)")

    async def fetch(self, query: str) -> str | None:
        """Return lyrics text for a song query. Placeholder."""
        logger.info("Fetch lyrics (placeholder): %s", query[:60])
        return None

    async def start_live(self, query: str | None = None) -> None:
        """Begin posting timed lyrics lines to chat. Placeholder."""
        self._live_active = True
        logger.info("Live lyrics started (placeholder): %s", query or "current track")

    async def stop_live(self) -> None:
        """Stop live lyrics streaming."""
        self._live_active = False
        logger.info("Live lyrics stopped")

    @property
    def is_live(self) -> bool:
        return self._live_active
