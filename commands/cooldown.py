"""
Per-user command cooldown tracking.

Prevents command spam.  Owner and delegated users bypass cooldowns by default.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from utils.constants import CommandSpec
from utils.helpers import normalize_username
from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig
    from utils.permissions import PermissionManager

logger = get_logger(__name__)


class CooldownManager:
    """Track last-use timestamps per (user, command) pair."""

    def __init__(self, config: BotConfig, permissions: PermissionManager) -> None:
        self._config = config
        self._permissions = permissions
        self._last_use: dict[tuple[str, str], float] = {}

    def check(self, username: str, spec: CommandSpec) -> tuple[bool, float]:
        """
        Return (allowed, seconds_remaining).

        Owner/delegated users skip cooldown.  spec.cooldown of 0 disables it.
        """
        if self._permissions.is_delegated(username):
            return True, 0.0

        cooldown_sec = spec.cooldown if spec.cooldown is not None else self._config.command_cooldown
        if cooldown_sec <= 0:
            return True, 0.0

        key = (normalize_username(username), spec.name)
        last = self._last_use.get(key)
        if last is None:
            return True, 0.0

        elapsed = time.monotonic() - last
        remaining = cooldown_sec - elapsed
        if remaining > 0:
            logger.debug(
                "Cooldown active for %s on /%s (%.1fs remaining)",
                username,
                spec.name,
                remaining,
            )
            return False, remaining

        return True, 0.0

    def record(self, username: str, command_name: str) -> None:
        """Mark a command as used for cooldown purposes."""
        key = (normalize_username(username), command_name)
        self._last_use[key] = time.monotonic()

    def clear_user(self, username: str) -> None:
        """Reset all cooldowns for a user."""
        name = normalize_username(username)
        keys = [k for k in self._last_use if k[0] == name]
        for key in keys:
            del self._last_use[key]
        logger.info("Cooldowns cleared for %s", username)

    def clear_all(self) -> None:
        self._last_use.clear()
        logger.info("All command cooldowns cleared")
