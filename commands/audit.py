"""
Structured command audit logging.

Every dispatch attempt is logged with user, command, args, outcome, and
duration for debugging and moderation review.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from commands.parser import ParsedCommand
from commands.result import CommandResult, DispatchStatus
from utils.logger import get_logger

audit_logger = get_logger("commands.audit")


@dataclass
class AuditRecord:
    """Single command dispatch audit entry."""

    username: str
    invoked_as: str
    command: str
    args: list[str]
    status: DispatchStatus
    success: bool
    message: str = ""
    duration_ms: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_log_line(self) -> str:
        args_str = " ".join(self.args) if self.args else ""
        return (
            f"user={self.username} cmd=/{self.command} invoked=/{self.invoked_as} "
            f"args=[{args_str}] status={self.status.name} ok={self.success} "
            f"ms={self.duration_ms:.0f} msg={self.message[:80]!r}"
        )


class CommandAuditLog:
    """Records and logs command dispatch events."""

    def log_attempt(self, cmd: ParsedCommand) -> float:
        """Return monotonic start time for duration tracking."""
        audit_logger.info(
            "RECV user=%s cmd=/%s invoked=/%s args=%s fp=%s",
            cmd.username,
            cmd.name,
            cmd.invoked_as,
            cmd.args,
            cmd.fingerprint[:8] if cmd.fingerprint else "",
        )
        return time.monotonic()

    def log_result(
        self,
        cmd: ParsedCommand,
        result: CommandResult,
        start: float,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        duration_ms = (time.monotonic() - start) * 1000
        record = AuditRecord(
            username=cmd.username,
            invoked_as=cmd.invoked_as,
            command=cmd.name,
            args=cmd.args,
            status=result.status,
            success=result.success,
            message=result.message,
            duration_ms=duration_ms,
            extra=extra or {},
        )
        level = "info" if result.success else "warning"
        getattr(audit_logger, level)(record.to_log_line())

    def log_denied(self, cmd: ParsedCommand, reason: str, start: float) -> None:
        result = CommandResult.fail(reason, status=DispatchStatus.DENIED)
        self.log_result(cmd, result, start)

    def log_cooldown(self, cmd: ParsedCommand, remaining: float, start: float) -> None:
        msg = f"Slow down — try again in {remaining:.0f}s."
        result = CommandResult.fail(msg, status=DispatchStatus.COOLDOWN)
        self.log_result(cmd, result, start)
