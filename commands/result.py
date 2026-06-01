"""Command execution results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class DispatchStatus(Enum):
    SUCCESS = auto()
    ERROR = auto()
    DENIED = auto()
    COOLDOWN = auto()
    UNKNOWN = auto()
    INVALID = auto()


@dataclass
class CommandResult:
    success: bool
    message: str = ""
    silent: bool = False
    status: DispatchStatus = DispatchStatus.SUCCESS

    @classmethod
    def ok(cls, message: str = "", *, silent: bool = False) -> CommandResult:
        return cls(True, message, silent=silent, status=DispatchStatus.SUCCESS)

    @classmethod
    def fail(
        cls,
        message: str,
        *,
        status: DispatchStatus = DispatchStatus.ERROR,
        silent: bool = False,
    ) -> CommandResult:
        return cls(False, message, silent=silent, status=status)
