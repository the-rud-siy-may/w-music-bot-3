"""
Bot runtime — poll Wakie chat, dispatch commands, play music.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from commands.dispatcher import CommandDispatcher
from commands.parser import CommandParser, ParseError
from commands.registry import registry
from player.audio_player import AudioPlayer
from player.local_autoplay import LocalAutoplayManager
from player.autoplay_manager import AutoplayManager
from player.downloader import Downloader
from player.playback_engine import PlaybackEngine
from player.stream_queue import StreamQueueManager
from player.volume_manager import VolumeManager
from player.youtube_service import YouTubeService
from utils.logger import get_logger
from utils.permissions import PermissionManager
from wakie.detector import MessageDetector
from wakie.device_session import DeviceSession
from wakie.message_filter import MessageFilter
from wakie.reader import MessageReader
from wakie.sender import MessageSender
from wakie.ui_mapper import UIMapper

if TYPE_CHECKING:
    from config import BotConfig

logger = get_logger(__name__)


class WakieBot:
    """Wakie streaming music bot."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._running = False

        self._session = DeviceSession(config)
        self._ui = UIMapper.from_package(config.wakie_package)
        self._message_filter = MessageFilter(config)
        self._reader = MessageReader(config, self._ui, session=self._session)
        self._sender = MessageSender(config, self._ui, session=self._session, message_filter=self._message_filter)
        self._detector = MessageDetector(config, message_filter=self._message_filter)

        self._volume = VolumeManager(config)
        self._queue = StreamQueueManager(config)
        self._youtube = YouTubeService(timeout=config.ytdlp_timeout)

        if config.use_local_autoplay:
            self._autoplay = LocalAutoplayManager(config)
        else:
            self._autoplay = AutoplayManager(config, self._youtube)
        self._queue.bind_autoplay(self._autoplay)

        self._downloader = Downloader(config)
        self._player = AudioPlayer(config, self._volume)

        self._permissions = PermissionManager(config, registry)
        self._parser = CommandParser()
        self._dispatcher = CommandDispatcher(
            config=config,
            permissions=self._permissions,
            sender=self._sender,
            queue=self._queue,
            player=self._player,
            volume=self._volume,
            downloader=self._downloader,
            youtube=self._youtube,
            autoplay=self._autoplay,
        )

        self._playback = PlaybackEngine(
            config=config,
            queue=self._queue,
            player=self._player,
            youtube=self._youtube,
            autoplay=self._autoplay,
            sender=self._sender,
        )

    async def start(self) -> None:
        logger.info("=== Wakie Music Bot starting ===")
        self._running = True

        await self._autoplay.load()
        await self._session.connect()
        await self._reader.connect()
        await self._sender.connect()
        await self._player.initialize()

        await asyncio.gather(
            self._poll_loop(),
            self._playback.run(lambda: self._running),
        )

    async def stop(self) -> None:
        self._running = False
        await self._player.shutdown()
        await self._reader.disconnect()
        await self._sender.disconnect()
        await self._session.disconnect()
        logger.info("Bot stopped")

    async def _poll_loop(self) -> None:
        logger.info("Poll loop started (interval=%.1fs)", self._config.poll_interval)

        while self._running:
            try:
                messages = await self._reader.read_messages()
                if messages:
                    new_messages = self._detector.filter_new_messages(messages)
                    for msg, fp in self._detector.extract_commands(new_messages):
                        parsed = self._parser.parse(msg.text, username=msg.username, fingerprint=fp)
                        if parsed is None:
                            continue
                        if isinstance(parsed, ParseError):
                            parsed.source_message = msg
                            await self._dispatcher.dispatch(parsed)
                            continue
                        parsed.source_message = msg
                        logger.info("Command: /%s from %s", parsed.name, msg.username)
                        await self._dispatcher.dispatch(parsed)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Poll loop error: %s", exc, exc_info=True)

            await asyncio.sleep(self._config.poll_interval)
