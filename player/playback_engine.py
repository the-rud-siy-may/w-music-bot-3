"""
VLC playback engine — streaming, retries, autoplay, and stream refresh.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable, Awaitable

from utils.helpers import truncate
from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig
    from player.audio_player import AudioPlayer
    from player.autoplay_manager import AutoplayManager
    from player.models import QueueEntry
    from player.stream_queue import StreamQueueManager
    from player.youtube_service import YouTubeService
    from wakie.sender import MessageSender

logger = get_logger(__name__)


class PlaybackEngine:
    """
    Drives continuous playback:
      - VLC stream/file playback
      - Stream URL refresh on expiry
      - Autoplay fallback when user queue empty
      - Retry with graceful recovery
    """

    def __init__(
        self,
        config: BotConfig,
        queue: StreamQueueManager,
        player: AudioPlayer,
        youtube: YouTubeService,
        autoplay: AutoplayManager,
        sender: MessageSender,
    ) -> None:
        self._config = config
        self._queue = queue
        self._player = player
        self._youtube = youtube
        self._autoplay = autoplay
        self._sender = sender
        self._running = False
        self._notified_autoplay = False
        self._max_retries = config.playback_max_retries

    async def run(self, is_running: Callable[[], bool]) -> None:
        """Main playback loop — call from bot runtime."""
        self._running = True
        logger.info("Playback engine started")

        while is_running():
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Playback engine error: %s", exc, exc_info=True)

            await asyncio.sleep(0.5)

        self._running = False
        logger.info("Playback engine stopped")

    async def _tick(self) -> None:
        # Track finished normally
        if self._player.has_finished() and self._player.current_track is not None:
            finished = await self._queue.consume_current()
            if finished:
                logger.info("Track finished: %s", finished.title)
            self._player.mark_idle()
            await self._queue.on_user_queue_drained()

        # Playback error — try refresh
        if self._player.has_error() and self._player.current_track is not None:
            await self._recover_current_stream()

        # Start next track when idle
        if not self._player.is_playing() and not self._player.is_buffering():
            await self._play_next_available()

    def _was_completely_silent(self) -> bool:
        """True only when nothing is playing and no track was active (cold start)."""
        return (
            self._queue.current is None
            and self._player.current_track is None
            and not self._player.is_playing()
            and not self._player.is_buffering()
        )

    async def _play_next_available(self) -> None:
        notify_loading = self._was_completely_silent()
        nxt = await self._queue.pop_next()

        if nxt is None:
            resumed = await self._queue.on_user_queue_drained()
            if resumed and not self._notified_autoplay:
                await self._notify("Queue empty — switching to local autoplay")
                self._notified_autoplay = True

            await self._queue.ensure_autoplay_track()
            nxt = await self._queue.pop_next()

        if nxt is None:
            return

        if nxt.source == "user":
            self._notified_autoplay = False

        await self._play_with_retry(nxt, notify_loading=notify_loading)

    async def _play_with_retry(self, entry: QueueEntry, *, notify_loading: bool = False) -> None:
        for attempt in range(1, self._max_retries + 1):
            try:
                await self._queue.set_current(entry)
                if attempt == 1 and notify_loading:
                    await self._notify(f"⏳ Loading: {truncate(entry.title)}...")
                await self._player.play(entry)
                logger.info("Now playing: %s (attempt %d)", entry.title, attempt)
                await self._notify(f"Now playing: {entry.title}")
                return
            except Exception as exc:
                logger.warning(
                    "Playback failed for %s (attempt %d/%d): %s",
                    entry.title,
                    attempt,
                    self._max_retries,
                    exc,
                )
                if entry.youtube_url and attempt < self._max_retries:
                    try:
                        entry = await self._youtube.refresh_stream(entry)
                        logger.info("Stream URL refreshed for: %s", entry.title)
                    except Exception as refresh_exc:
                        logger.error("Stream refresh failed: %s", refresh_exc)

                await asyncio.sleep(self._config.playback_retry_delay)

        logger.error("Giving up on track: %s", entry.title)
        await self._notify(f"Could not play: {entry.title}")
        await self._queue.consume_current()
        self._player.mark_idle()

    async def _recover_current_stream(self) -> None:
        entry = self._player.current_track
        if entry is None:
            return

        logger.warning("Recovering from playback error: %s", entry.title)
        await self._player.stop()

        if entry.youtube_url:
            try:
                entry = await self._youtube.refresh_stream(entry)
                await self._play_with_retry(entry)
                return
            except Exception as exc:
                logger.error("Recovery failed: %s", exc)

        await self._queue.consume_current()
        self._player.mark_idle()

    async def _notify(self, message: str) -> None:
        try:
            await self._sender.send(message)
        except Exception as exc:
            logger.debug("Playback notify failed: %s", exc)
