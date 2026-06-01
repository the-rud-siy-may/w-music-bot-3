"""
Public command handlers.
"""

from __future__ import annotations

import asyncio

from commands.base import BaseCommandModule
from commands.parser import ParsedCommand
from commands.registry import registry
from commands.result import CommandResult
from player.local_library import resolve_local_song
from player.models import QueueEntry
from utils.helpers import safe_int, truncate
from utils.track_duration import check_local_file, check_stream_info
from utils.logger import get_logger

logger = get_logger(__name__)


class PublicCommands(BaseCommandModule):
    handlers: dict

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.handlers = {
            "add": self.cmd_add,
            "q": self.cmd_q,
            "np": self.cmd_np,
            "upnext": self.cmd_upnext,
            "remove": self.cmd_remove,
            "skip": self.cmd_skip,
            "clear": self.cmd_clear,
            "volume": self.cmd_volume,
            "status": self.cmd_status,
            "greet": self.cmd_greet,
            "help": self.cmd_help,
        }

    def _is_mod(self, username: str) -> bool:
        return self._permissions.is_moderator(username)

    async def cmd_add(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            return CommandResult.fail("Usage: /add <song name or YouTube URL>")

        query = cmd.arg_text
        max_dur = float(self._config.max_track_duration_seconds)

        local_path = resolve_local_song(query, self._config.songs_dir)
        if local_path is not None:
            duration_err = await asyncio.to_thread(check_local_file, local_path, max_dur)
            if duration_err:
                return CommandResult.fail(duration_err)

            entry = QueueEntry.create(
                title=local_path.stem.replace("_", " ").title(),
                query=query,
                file_path=str(local_path),
                requested_by=cmd.username,
                source="user",
            )
            await self._queue.add_user(entry)
            pos = self._queue.position_of(entry.id)
            return CommandResult.ok(f"Added: {truncate(entry.title)} (#{pos})")

        try:
            info = await self._youtube.extract_stream(query)
        except Exception as exc:
            logger.error("YouTube extract failed: %s", exc)
            return CommandResult.fail(f"Could not find: {query}")

        duration_err = check_stream_info(info, max_dur)
        if duration_err:
            return CommandResult.fail(duration_err)

        entry = QueueEntry.from_stream_info(info, requested_by=cmd.username, source="user")
        await self._queue.add_user(entry)
        pos = self._queue.position_of(entry.id)
        return CommandResult.ok(f"Added: {truncate(entry.title)} (#{pos})")

    async def cmd_q(self, cmd: ParsedCommand) -> CommandResult:
        listing = self._queue.format_listing()
        if not listing:
            return CommandResult.ok("Queue is empty.")
        return CommandResult.ok(f"Queue ({self._queue.length}):\n{listing}")

    async def cmd_np(self, cmd: ParsedCommand) -> CommandResult:
        current = self._queue.current or self._player.current_track
        if current is None:
            return CommandResult.ok("Nothing playing.")
        return CommandResult.ok(f"Now playing: {truncate(current.title)}")

    async def cmd_upnext(self, cmd: ParsedCommand) -> CommandResult:
        nxt = self._queue.peek_next()
        if nxt is None:
            return CommandResult.ok("Nothing queued next.")
        return CommandResult.ok(f"Up next: {truncate(nxt.title)}")

    async def cmd_remove(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            return CommandResult.fail("Usage: /remove <number>")
        num = safe_int(cmd.args[0])
        if num is None or num < 1:
            return CommandResult.fail("Invalid queue number.")
        removed, err = await self._queue.remove_at(
            num,
            username=cmd.username,
            is_moderator=self._is_mod(cmd.username),
        )
        if removed is None:
            return CommandResult.fail(err)
        return CommandResult.ok(f"Removed: {truncate(removed.title)}")

    async def cmd_skip(self, cmd: ParsedCommand) -> CommandResult:
        ok, reason = self._queue.can_skip_current(
            cmd.username,
            is_moderator=self._is_mod(cmd.username),
        )
        if not ok:
            return CommandResult.fail(reason)
        skipped = await self._queue.consume_current()
        await self._player.stop()
        if skipped:
            return CommandResult.ok(f"Skipped: {truncate(skipped.title)}")
        return CommandResult.ok("Nothing to skip.")

    async def cmd_clear(self, cmd: ParsedCommand) -> CommandResult:
        mod = self._is_mod(cmd.username)
        count = await self._queue.clear_for_user(cmd.username, is_moderator=mod)
        await self._queue.on_user_queue_drained()
        return CommandResult.ok(f"Cleared {count} request(s).")

    async def cmd_volume(self, cmd: ParsedCommand) -> CommandResult:
        return CommandResult.ok(f"Volume: {self._volume.current}%")

    async def cmd_status(self, cmd: ParsedCommand) -> CommandResult:
        current = self._queue.current
        title = truncate(current.title) if current else "none"
        flags = []
        if self._config.muted:
            flags.append("muted")
        if self._config.locked:
            flags.append("locked")
        extra = f" ({', '.join(flags)})" if flags else ""
        return CommandResult.ok(
            f"{self._player.state_label} | {title} | queue {self._queue.length}{extra}",
        )

    async def cmd_greet(self, cmd: ParsedCommand) -> CommandResult:
        return CommandResult.ok(f"Hey {cmd.username}!")

    async def cmd_help(self, cmd: ParsedCommand) -> CommandResult:
        tier = self._permissions.tier_for_user(cmd.username)
        return CommandResult.ok(registry.help_text(tier))
