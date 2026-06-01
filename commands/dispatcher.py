"""
Command dispatcher — routes parsed commands to handlers.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from commands.audit import CommandAuditLog
from commands.base import BaseCommandModule, HandlerContext, HandlerFn
from commands.cooldown import CooldownManager
from commands.delegated_commands import DelegatedCommands
from commands.owner_commands import OwnerCommands
from commands.parser import ParseError, ParsedCommand
from commands.public_commands import PublicCommands
from commands.registry import registry
from commands.result import CommandResult, DispatchStatus
from utils.constants import CommandTier
from utils.helpers import normalize_username
from utils.logger import get_logger
from utils.permissions import PermissionManager

if TYPE_CHECKING:
    from config import BotConfig
    from player.audio_player import AudioPlayer
    from player.autoplay_manager import AutoplayManager
    from player.downloader import Downloader
    from player.stream_queue import StreamQueueManager
    from player.volume_manager import VolumeManager
    from player.youtube_service import YouTubeService
    from wakie.sender import MessageSender

logger = get_logger(__name__)


class CommandDispatcher:
    def __init__(
        self,
        config: BotConfig,
        permissions: PermissionManager,
        sender: MessageSender,
        queue: StreamQueueManager,
        player: AudioPlayer,
        volume: VolumeManager,
        downloader: Downloader,
        youtube: YouTubeService,
        autoplay: AutoplayManager,
    ) -> None:
        self._config = config
        self._permissions = permissions
        self._sender = sender
        self._registry = registry
        self._cooldowns = CooldownManager(config, permissions)
        self._audit = CommandAuditLog()
        self._unknown_last: dict[tuple[str, str], float] = {}

        ctx = HandlerContext(
            config=config,
            queue=queue,
            player=player,
            volume=volume,
            downloader=downloader,
            permissions=permissions,
            youtube=youtube,
            autoplay=autoplay,
        )

        self._handlers: dict[str, HandlerFn] = {}
        self._register_modules(
            PublicCommands(ctx),
            DelegatedCommands(ctx),
            OwnerCommands(ctx),
        )

    def _register_modules(self, *modules: BaseCommandModule) -> None:
        for module in modules:
            for name, fn in module.get_handlers().items():
                if name not in self._handlers:
                    self._handlers[name] = fn

    async def dispatch(self, cmd: ParsedCommand | ParseError) -> CommandResult:
        if isinstance(cmd, ParseError):
            result = CommandResult.fail(cmd.reason, status=DispatchStatus.INVALID)
            await self._respond(result)
            return result

        start = self._audit.log_attempt(cmd)
        spec = cmd.spec

        if spec is None:
            if self._should_suppress_unknown(cmd):
                result = CommandResult.fail("", status=DispatchStatus.UNKNOWN, silent=True)
                self._audit.log_result(cmd, result, start)
                return result
            msg = self._registry.unknown_command_message(cmd.invoked_as or cmd.name)
            result = CommandResult.fail(msg, status=DispatchStatus.UNKNOWN)
            self._record_unknown(cmd)
            self._audit.log_result(cmd, result, start)
            await self._respond(result)
            return result

        allowed, remaining = self._cooldowns.check(cmd.username, spec)
        if not allowed:
            result = CommandResult.fail(
                f"Slow down — try /{cmd.name} again in {remaining:.0f}s.",
                status=DispatchStatus.COOLDOWN,
            )
            await self._respond(result)
            return result

        perm_ok, reason = self._permissions.can_execute(cmd.username, cmd.name)
        if not perm_ok:
            result = CommandResult.fail(reason, status=DispatchStatus.DENIED)
            self._audit.log_denied(cmd, reason, start)
            await self._respond(result)
            return result

        handler = self._handlers.get(cmd.name)
        if handler is None:
            result = CommandResult.fail(f"/{cmd.name} has no handler.", status=DispatchStatus.ERROR)
            await self._respond(result)
            return result

        try:
            result = await handler(cmd)
            if result.status == DispatchStatus.SUCCESS and not result.success:
                result = CommandResult.fail(result.message or "Command failed.")
        except Exception as exc:
            logger.error("Error running /%s: %s", cmd.name, exc, exc_info=True)
            result = CommandResult.fail("Something went wrong.")

        self._cooldowns.record(cmd.username, cmd.name)
        self._audit.log_result(cmd, result, start)
        await self._respond(result)
        return result

    def _should_suppress_unknown(self, cmd: ParsedCommand) -> bool:
        key = (normalize_username(cmd.username), (cmd.invoked_as or cmd.name).lower())
        last = self._unknown_last.get(key)
        if last is None:
            return False
        return (time.monotonic() - last) < self._config.unknown_cmd_cooldown

    def _record_unknown(self, cmd: ParsedCommand) -> None:
        key = (normalize_username(cmd.username), (cmd.invoked_as or cmd.name).lower())
        self._unknown_last[key] = time.monotonic()

    async def _respond(self, result: CommandResult) -> None:
        if result.message and not result.silent and not self._config.muted:
            await self._sender.send(result.message)
