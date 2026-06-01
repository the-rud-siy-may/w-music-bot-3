"""
Delegated (moderator) command handlers.
"""

from __future__ import annotations

from commands.base import BaseCommandModule
from commands.parser import ParsedCommand
from commands.result import CommandResult
from utils.helpers import safe_int


class DelegatedCommands(BaseCommandModule):
    handlers: dict

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.handlers = {
            "pause": self.cmd_pause,
            "resume": self.cmd_resume,
            "stop": self.cmd_stop,
            "vol": self.cmd_vol,
            "loop": self.cmd_loop,
        }

    async def cmd_pause(self, cmd: ParsedCommand) -> CommandResult:
        await self._player.pause()
        return CommandResult.ok("Paused.")

    async def cmd_resume(self, cmd: ParsedCommand) -> CommandResult:
        await self._player.resume()
        return CommandResult.ok("Resumed.")

    async def cmd_stop(self, cmd: ParsedCommand) -> CommandResult:
        await self._player.stop()
        return CommandResult.ok("Playback stopped.")

    async def cmd_vol(self, cmd: ParsedCommand) -> CommandResult:
        if not cmd.args:
            return CommandResult.fail("Usage: /vol <0-200>")
        level = safe_int(cmd.args[0])
        if level is None or not (0 <= level <= self._config.max_volume):
            return CommandResult.fail(f"Volume must be 0–{self._config.max_volume}.")
        self._volume.set(level)
        await self._player.apply_volume(level)
        return CommandResult.ok(f"Volume: {level}%")

    async def cmd_loop(self, cmd: ParsedCommand) -> CommandResult:
        enabled = await self._queue.toggle_loop()
        return CommandResult.ok(f"Loop: {'on' if enabled else 'off'}")
