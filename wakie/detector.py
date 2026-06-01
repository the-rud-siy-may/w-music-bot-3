"""
Detect new chat messages and extract slash-commands.
"""

from __future__ import annotations

import re
import time
from collections import deque
from typing import TYPE_CHECKING

from utils.helpers import command_fingerprint, normalize_command_text, normalize_username
from utils.logger import get_logger
from wakie.message_filter import MessageFilter
from wakie.reader import ChatMessage

if TYPE_CHECKING:
    from config import BotConfig

logger = get_logger(__name__)

_CMD_RE = re.compile(r"(?:^|\n)\s*(/\S[^\n]*)", re.MULTILINE)
_DEDUP_SECONDS = 60.0


class MessageDetector:
    def __init__(self, config: BotConfig, message_filter: MessageFilter | None = None) -> None:
        self._config = config
        self._filter = message_filter or MessageFilter(config)
        self._seen_ids: set[str] = set()
        self._recent_commands: deque[tuple[float, str]] = deque(maxlen=config.max_processed_cache)

    @property
    def filter(self) -> MessageFilter:
        return self._filter

    @staticmethod
    def _command_line(text: str) -> str | None:
        match = _CMD_RE.search(text.strip())
        if not match:
            return None
        line = match.group(1).strip()
        return line if line.startswith("/") else None

    def filter_new_messages(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        new: list[ChatMessage] = []
        for msg in messages:
            if msg.message_id in self._seen_ids:
                continue
            self._seen_ids.add(msg.message_id)

            allowed, reason = self._filter.should_process(msg)
            if not allowed:
                logger.debug("Skipped message (%s): %s", reason, msg.message[:50])
                continue
            new.append(msg)
        return new

    def _is_duplicate(self, key: str) -> bool:
        now = time.monotonic()
        while self._recent_commands and now - self._recent_commands[0][0] > _DEDUP_SECONDS:
            self._recent_commands.popleft()
        return any(k == key for _, k in self._recent_commands)

    def extract_commands(self, messages: list[ChatMessage]) -> list[tuple[ChatMessage, str]]:
        out: list[tuple[ChatMessage, str]] = []
        for msg in messages:
            cmd_line = self._command_line(msg.message)
            if cmd_line is None:
                continue
            if self._filter.is_self_user(msg.username):
                continue
            if self._filter.is_bot_generated_text(cmd_line):
                continue

            dedup_key = normalize_command_text(cmd_line)
            user = normalize_username(msg.username)
            if user and user not in ("unknown", "?"):
                dedup_key = f"{user}|{dedup_key}"

            if self._is_duplicate(dedup_key):
                logger.info("Duplicate command ignored: %s", cmd_line[:60])
                continue

            self._recent_commands.append((time.monotonic(), dedup_key))
            fp = command_fingerprint(msg.username, cmd_line, msg.timestamp.timestamp())
            out.append((msg, fp))
            logger.info("Command from %s: %s", msg.username, cmd_line[:80])
        return out
