"""
Volume management for playback.

Centralises volume state and clamping to configured max.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig

logger = get_logger(__name__)


class VolumeManager:
    """Track and clamp playback volume (0 – max_volume)."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._current: int = config.default_volume
        logger.debug("VolumeManager initial volume: %d", self._current)

    @property
    def current(self) -> int:
        return self._current

    def set(self, level: int) -> int:
        """Clamp and store a new volume level; return the applied value."""
        clamped = max(0, min(level, self._config.max_volume))
        self._current = clamped
        logger.info("Volume → %d", clamped)
        return clamped

    def increase(self, delta: int = 10) -> int:
        return self.set(self._current + delta)

    def decrease(self, delta: int = 10) -> int:
        return self.set(self._current - delta)
