"""
Filter bot self-messages and obvious bot reply text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.bot_messages import BOT_RESPONSE_PREFIXES
from utils.helpers import display_names_match, normalize_username
from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig
    from wakie.reader import ChatMessage

logger = get_logger(__name__)


class MessageFilter:
    def __init__(self, config: BotConfig) -> None:
        self._bot_username = normalize_username(config.bot_username)
        self._bot_username_raw = (config.bot_username or "").strip()
        self._outbound: list[str] = []

        if self._bot_username:
            logger.info("Bot username filter: %s", config.bot_username)

    def register_outbound(self, text: str) -> None:
        t = text.strip().lower()
        if t:
            self._outbound.append(t)
            if len(self._outbound) > 100:
                self._outbound = self._outbound[-100:]

    def should_process(self, msg: ChatMessage) -> tuple[bool, str]:
        if self.is_self_user(msg.username):
            return False, "self"
        if self.is_bot_generated_text(msg.message):
            return False, "bot_text"
        lower = msg.message.strip().lower()
        if any(lower == s or lower.startswith(s) for s in self._outbound):
            return False, "outbound"
        return True, ""

    def is_self_user(self, username: str) -> bool:
        if not self._bot_username:
            return False
        name = normalize_username(username)
        if name == self._bot_username or name == "you":
            return True
        if self._bot_username_raw and display_names_match(self._bot_username_raw, username):
            return True
        return False

    def is_bot_generated_text(self, text: str) -> bool:
        lower = text.strip().lower()
        if not lower:
            return True
        if any(lower.startswith(p) for p in BOT_RESPONSE_PREFIXES):
            return True
        if lower.startswith("unknown command"):
            return True
        return False
