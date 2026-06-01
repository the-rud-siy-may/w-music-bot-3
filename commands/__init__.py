"""Command parsing and dispatch layer."""

from commands.parser import CommandParser, ParsedCommand, ParseError
from commands.dispatcher import CommandDispatcher
from commands.result import CommandResult, DispatchStatus
from commands.registry import registry, CommandRegistry
from commands.cooldown import CooldownManager
from commands.base import HandlerContext, BaseCommandModule

__all__ = [
    "CommandParser",
    "ParsedCommand",
    "ParseError",
    "CommandDispatcher",
    "CommandResult",
    "DispatchStatus",
    "registry",
    "CommandRegistry",
    "CooldownManager",
    "HandlerContext",
    "BaseCommandModule",
]
