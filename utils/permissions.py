"""
Permission checks for command tiers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import BotConfig
from utils.constants import CommandTier, TIER_ORDER
from utils.helpers import display_names_match, normalize_username
from utils.logger import get_logger

if TYPE_CHECKING:
    from commands.registry import CommandRegistry

logger = get_logger(__name__)


class PermissionManager:
    def __init__(self, config: BotConfig, registry: CommandRegistry) -> None:
        self._config = config
        self._registry = registry
        self._blocked: set[str] = set()

    def is_owner(self, username: str) -> bool:
        if not self._config.owner_username:
            return False
        if normalize_username(username) == self._config.owner_username:
            return True
        return display_names_match(self._config.owner_username, username)

    def is_delegated(self, username: str) -> bool:
        name = normalize_username(username)
        return name in self._config.delegated_users or self.is_owner(name)

    def is_moderator(self, username: str) -> bool:
        return self.is_delegated(username)

    def tier_for_user(self, username: str) -> CommandTier:
        if self.is_owner(username):
            return CommandTier.OWNER
        if self.is_delegated(username):
            return CommandTier.DELEGATED
        return CommandTier.PUBLIC

    def block_user(self, username: str) -> None:
        self._blocked.add(normalize_username(username))

    def unblock_user(self, username: str) -> None:
        self._blocked.discard(normalize_username(username))

    def is_blocked(self, username: str) -> bool:
        return normalize_username(username) in self._blocked

    def can_execute(self, username: str, command_name: str) -> tuple[bool, str]:
        name = normalize_username(username)
        if self.is_blocked(name):
            return False, "You are blocked."

        spec = self._registry.get(command_name)
        if spec is None:
            return False, f"Unknown command: /{command_name}"

        if self._config.locked and spec.tier == CommandTier.PUBLIC:
            if not self.is_delegated(name):
                return False, "Bot is locked."

        user_tier = self.tier_for_user(name)
        if TIER_ORDER[user_tier] < TIER_ORDER[spec.tier]:
            return False, "No permission for that command."

        return True, ""
