"""
VLC-based audio player — local files and YouTube stream URLs.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig
    from player.models import QueueEntry
    from player.volume_manager import VolumeManager

logger = get_logger(__name__)


class PlayerState(Enum):
    IDLE = auto()
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()
    BUFFERING = auto()
    ERROR = auto()


class AudioPlayer:
    """python-vlc wrapper with stream and file support."""

    def __init__(self, config: BotConfig, volume: VolumeManager) -> None:
        self._config = config
        self._volume = volume
        self._state = PlayerState.IDLE
        self._current: QueueEntry | None = None
        self._instance = None
        self._player = None
        self._vlc = None
        self._buffer_timeout = config.playback_buffer_timeout

    @property
    def state(self) -> PlayerState:
        return self._state

    @property
    def state_label(self) -> str:
        return self._state.name.lower()

    @property
    def current_track(self) -> QueueEntry | None:
        return self._current

    async def initialize(self) -> None:
        def _init() -> None:
            import vlc

            self._vlc = vlc
            args: list[str] = []
            if self._config.vlc_audio_device:
                args.extend(["--aout=directsound"])
            # Network caching for streams (ms)
            args.extend(["--network-caching=3000", "--live-caching=3000"])
            self._instance = vlc.Instance(" ".join(args))
            self._player = self._instance.media_player_new()
            logger.info("VLC initialized (streaming enabled)")

        await asyncio.to_thread(_init)

    async def play(self, entry: QueueEntry) -> None:
        url = entry.playable_url()
        if not url:
            raise ValueError(f"No playable URL for: {entry.title}")

        if url.startswith("http://") or url.startswith("https://"):
            await asyncio.to_thread(self._play_stream_sync, entry, url)
        else:
            path = Path(url)
            if not path.is_file():
                raise FileNotFoundError(f"Audio file not found: {path}")
            await asyncio.to_thread(self._play_file_sync, entry, path)

        await self._wait_for_buffering()

    def _play_stream_sync(self, entry: QueueEntry, url: str) -> None:
        if self._player is None or self._instance is None:
            raise RuntimeError("VLC not initialized")

        if self._player.is_playing():
            self._player.stop()

        media = self._instance.media_new(url)
        media.add_option(":network-caching=3000")
        self._player.set_media(media)
        self._player.audio_set_volume(self._volume.current)
        self._player.play()

        self._current = entry
        self._state = PlayerState.BUFFERING
        logger.info("Streaming: %s", entry.title)

    def _play_file_sync(self, entry: QueueEntry, path: Path) -> None:
        if self._player is None or self._instance is None:
            raise RuntimeError("VLC not initialized")

        if self._player.is_playing():
            self._player.stop()

        media = self._instance.media_new(str(path))
        self._player.set_media(media)
        self._player.audio_set_volume(self._volume.current)
        self._player.play()

        self._current = entry
        self._state = PlayerState.PLAYING
        logger.info("Playing file: %s", path.name)

    async def _wait_for_buffering(self) -> None:
        """Wait until VLC starts playing or errors out."""
        deadline = time.monotonic() + self._buffer_timeout

        while time.monotonic() < deadline:
            if self._player is None or self._vlc is None:
                return

            state = self._player.get_state()
            if state == self._vlc.State.Playing:
                self._state = PlayerState.PLAYING
                return
            if state == self._vlc.State.Error:
                self._state = PlayerState.ERROR
                raise RuntimeError("VLC entered error state during buffering")
            if state == self._vlc.State.Ended:
                return

            await asyncio.sleep(0.2)

        if self.is_playing():
            self._state = PlayerState.PLAYING
        else:
            logger.warning("Buffering timeout — continuing anyway")

    async def pause(self) -> None:
        await asyncio.to_thread(self._pause_sync)

    def _pause_sync(self) -> None:
        if self._player and self._player.is_playing():
            self._player.pause()
            self._state = PlayerState.PAUSED

    async def resume(self) -> None:
        await asyncio.to_thread(self._resume_sync)

    def _resume_sync(self) -> None:
        if self._player:
            self._player.play()
            self._state = PlayerState.PLAYING

    async def stop(self) -> None:
        await asyncio.to_thread(self._stop_sync)

    def _stop_sync(self) -> None:
        if self._player:
            self._player.stop()
        self._state = PlayerState.STOPPED
        # Keep _current so skip/queue advance is not treated as a cold start.

    async def skip(self) -> QueueEntry | None:
        skipped = self._current
        await self.stop()
        return skipped

    async def apply_volume(self, level: int) -> None:
        def _apply() -> None:
            if self._player:
                self._player.audio_set_volume(level)

        await asyncio.to_thread(_apply)

    def is_playing(self) -> bool:
        if self._player is None or self._vlc is None:
            return False
        return self._player.get_state() == self._vlc.State.Playing

    def is_buffering(self) -> bool:
        if self._player is None or self._vlc is None:
            return self._state == PlayerState.BUFFERING
        return self._player.get_state() in (
            self._vlc.State.Opening,
            self._vlc.State.Buffering,
        )

    def has_error(self) -> bool:
        if self._player is None or self._vlc is None:
            return self._state == PlayerState.ERROR
        return self._player.get_state() == self._vlc.State.Error

    def has_finished(self) -> bool:
        if self._player is None or self._vlc is None:
            return self._state in (PlayerState.IDLE, PlayerState.STOPPED)
        state = self._player.get_state()
        return state in (
            self._vlc.State.Ended,
            self._vlc.State.Stopped,
            self._vlc.State.NothingSpecial,
        )

    def mark_idle(self) -> None:
        self._state = PlayerState.IDLE

    async def shutdown(self) -> None:
        await self.stop()
        self._player = None
        self._instance = None
        logger.info("AudioPlayer shut down")
