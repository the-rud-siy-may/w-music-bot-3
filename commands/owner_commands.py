"""
Owner command handlers.
"""

from __future__ import annotations

from commands.base import BaseCommandModule
from commands.parser import ParsedCommand
from commands.result import CommandResult
from utils.helpers import safe_int, truncate
from utils.logger import get_logger

logger = get_logger(__name__)


class OwnerCommands(BaseCommandModule):
    handlers: dict

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.handlers = {
            "play": self.cmd_play,
            "addnext": self.cmd_addnext,
            "move": self.cmd_move,
            "topic": self.cmd_topic,
            "restart": self.cmd_restart,
            "lock": self.cmd_lock,
            "unlock": self.cmd_unlock,
            "mute": self.cmd_mute,
            "unmute": self.cmd_unmute,
            "block": self.cmd_block,
            "unblock": self.cmd_unblock,
            "clearcache": self.cmd_clearcache,
        }

    async def cmd_play(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            nxt = await self._queue.pop_next()
            if nxt is None:
                return CommandResult.fail("Queue is empty.")
            await self._player.play(nxt)
            return CommandResult.ok(f"Now playing: {truncate(nxt.title)}")
        entry = await self._queue.add(cmd.arg_text, requested_by=cmd.username, front=True)
        await self._player.play(entry)
        return CommandResult.ok(f"Playing: {truncate(entry.title)}")

    async def cmd_addnext(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            return CommandResult.fail("Usage: /addnext <song|url>")
        entry = await self._queue.add(
            cmd.arg_text,
            requested_by=cmd.username,
            insert_after_current=True,
        )
        return CommandResult.ok(f"Next: {truncate(entry.title)}")

    async def cmd_move(self, cmd: ParsedCommand) -> CommandResult:
        if len(cmd.args) < 2:
            return CommandResult.fail("Usage: /move <from> <to>")
        src = safe_int(cmd.args[0])
        dst = safe_int(cmd.args[1])
        if src is None or dst is None:
            return CommandResult.fail("Use numbers for positions.")
        if not await self._queue.move(src, dst):
            return CommandResult.fail("Could not move — check positions.")
        return CommandResult.ok(f"Moved #{src} → #{dst}")

    async def cmd_topic(self, cmd: ParsedCommand) -> CommandResult:
        return CommandResult.ok(f"Topic: {cmd.arg_text or 'Music'}")

    async def cmd_restart(self, cmd: ParsedCommand) -> CommandResult:
        logger.warning("Restart requested by %s", cmd.username)
        return CommandResult.ok("Restart requested (restart main.py manually).")

    async def cmd_lock(self, cmd: ParsedCommand) -> CommandResult:
        self._config.locked = True
        return CommandResult.ok("Public commands locked.")

    async def cmd_unlock(self, cmd: ParsedCommand) -> CommandResult:
        self._config.locked = False
        return CommandResult.ok("Public commands unlocked.")

    async def cmd_mute(self, cmd: ParsedCommand) -> CommandResult:
        self._config.muted = True
        return CommandResult.ok("Bot muted.")

    async def cmd_unmute(self, cmd: ParsedCommand) -> CommandResult:
        self._config.muted = False
        return CommandResult.ok("Bot unmuted.")

    async def cmd_block(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            return CommandResult.fail("Usage: /block <username>")
        self._permissions.block_user(cmd.args[0])
        return CommandResult.ok(f"Blocked {cmd.args[0]}.")

    async def cmd_unblock(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            return CommandResult.fail("Usage: /unblock <username>")
        self._permissions.unblock_user(cmd.args[0])
        return CommandResult.ok(f"Unblocked {cmd.args[0]}.")

    async def cmd_clearcache(self, cmd: ParsedCommand) -> CommandResult:
        count = await self._downloader.clear_cache()
        return CommandResult.ok(f"Cleared {count} cached file(s).")
