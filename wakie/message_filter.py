"""
Filter bot self-messages and reply-thread command previews.
"""

from __future__ import annotations

import re
import time
from collections import deque
from typing import TYPE_CHECKING

from utils.bot_messages import BOT_RESPONSE_PREFIXES
from utils.helpers import display_names_match, normalize_command_text, normalize_username
from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig
    from wakie.reader import ChatMessage

logger = get_logger(__name__)

_CMD_LINE_RE = re.compile(r"(?:^|\n)\s*(/\S.*)", re.MULTILINE)
_PREVIEW_ECHO_TTL_SECONDS = 25.0
_MASKED_USERNAMES = frozenset({"unknown", "?", ""})


class MessageFilter:
    def __init__(self, config: BotConfig) -> None:
        self._bot_username = normalize_username(config.bot_username)
        self._bot_username_raw = (config.bot_username or "").strip()
        self._outbound: deque[str] = deque(maxlen=150)
        # Recent full command lines we replied to (for reply-preview suppression only)
        self._handled_commands: deque[tuple[float, str]] = deque(maxlen=300)
        # Message IDs we already processed end-to-end
        self._handled_message_ids: deque[tuple[float, str]] = deque(maxlen=500)

        if self._bot_username:
            logger.info("Bot username filter: %s", config.bot_username)

    def register_outbound(self, text: str) -> None:
        normalized = text.strip().lower()
        if not normalized:
            return
        self._outbound.append(normalized)

    def register_command_handled(self, message: str, *, message_id: str = "") -> None:
        """Remember a command we are handling / responded to."""
        now = time.monotonic()
        for key in self._command_keys(message):
            self._handled_commands.append((now, key))
        if message_id:
            self._handled_message_ids.append((now, message_id))

    def should_process(self, msg: ChatMessage) -> tuple[bool, str]:
        if self.is_self_user(msg.username):
            logger.info("Ignored self user %s: %s", msg.username, msg.message[:60])
            return False, "self"

        if self._was_message_handled(msg.message_id):
            return False, "handled_id"

        if self.is_bot_generated_text(msg.message):
            logger.info("Ignored bot text: %s", msg.message[:60])
            return False, "bot_text"

        if self.matches_outbound(msg.message):
            logger.info("Ignored outbound echo: %s", msg.message[:60])
            return False, "outbound"

        if self.is_reply_preview(msg.message, msg.username):
            logger.info("Ignored reply preview: %s", msg.message[:60])
            return False, "reply_preview"

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
        if self._looks_like_help_listing(lower):
            return True
        return False

    def is_reply_preview(self, text: str, username: str) -> bool:
        """
        Reply threads re-show the original /command as a masked 'unknown' bubble.
        Only block that — never block real users (even if command text repeats).
        """
        user = normalize_username(username)
        if user not in _MASKED_USERNAMES:
            return False
        if not text.strip().startswith("/"):
            return False
        self._prune_handled()
        keys = self._command_keys(text)
        recent = {key for _, key in self._handled_commands}
        return bool(keys & recent)

    def matches_outbound(self, text: str) -> bool:
        """Match bot's own chat lines — not arbitrary song titles from queue text."""
        lower = text.strip().lower()
        if not lower:
            return False
        if any(lower.startswith(p) for p in BOT_RESPONSE_PREFIXES):
            return True
        for sent in self._outbound:
            if lower == sent:
                return True
            if lower.startswith(sent) and len(sent) >= 24:
                return True
        return False

    def _was_message_handled(self, message_id: str) -> bool:
        if not message_id:
            return False
        self._prune_handled()
        return any(mid == message_id for _, mid in self._handled_message_ids)

    def _looks_like_help_listing(self, lower: str) -> bool:
        if "music bot" in lower and "/" in lower:
            return True
        if "public (everyone)" in lower or "admin (mods)" in lower or "owner:" in lower:
            return True
        return len(_CMD_LINE_RE.findall(lower)) >= 3

    def _command_keys(self, text: str) -> set[str]:
        raw = text.strip()
        if not raw:
            return set()
        keys: set[str] = set()
        if raw.startswith("/"):
            keys.add(normalize_command_text(raw))
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("/"):
                keys.add(normalize_command_text(line))
        return keys

    def _prune_handled(self) -> None:
        now = time.monotonic()
        while self._handled_commands and now - self._handled_commands[0][0] > _PREVIEW_ECHO_TTL_SECONDS:
            self._handled_commands.popleft()
        while self._handled_message_ids and now - self._handled_message_ids[0][0] > _PREVIEW_ECHO_TTL_SECONDS * 4:
            self._handled_message_ids.popleft()
