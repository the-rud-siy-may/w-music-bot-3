"""
Shared handler infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, TYPE_CHECKING

from commands.parser import ParsedCommand
from commands.result import CommandResult

if TYPE_CHECKING:
    from config import BotConfig
    from player.audio_player import AudioPlayer
    from player.autoplay_manager import AutoplayManager
    from player.downloader import Downloader
    from player.stream_queue import StreamQueueManager
    from player.volume_manager import VolumeManager
    from player.youtube_service import YouTubeService
    from utils.permissions import PermissionManager

HandlerFn = Callable[[ParsedCommand], Awaitable[CommandResult]]


@dataclass
class HandlerContext:
    config: BotConfig
    queue: StreamQueueManager
    player: AudioPlayer
    volume: VolumeManager
    downloader: Downloader
    permissions: PermissionManager
    youtube: YouTubeService
    autoplay: AutoplayManager


class BaseCommandModule:
    handlers: dict[str, HandlerFn]

    def __init__(self, ctx: HandlerContext) -> None:
        self.ctx = ctx
        self._config = ctx.config
        self._queue = ctx.queue
        self._player = ctx.player
        self._volume = ctx.volume
        self._downloader = ctx.downloader
        self._permissions = ctx.permissions
        self._youtube = ctx.youtube
        self._autoplay = ctx.autoplay

    def get_handlers(self) -> dict[str, HandlerFn]:
        return dict(self.handlers)
