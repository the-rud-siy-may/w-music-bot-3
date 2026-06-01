"""
Parse slash-commands from chat text.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field

from commands.registry import registry
from utils.constants import COMMAND_PREFIX, CommandSpec
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ParsedCommand:
    raw: str
    name: str
    args: list[str] = field(default_factory=list)
    username: str = ""
    fingerprint: str = ""
    invoked_as: str = ""
    source_message: object | None = None

    @property
    def arg_text(self) -> str:
        return " ".join(self.args)

    @property
    def spec(self) -> CommandSpec | None:
        return registry.get(self.name)

    @property
    def is_known(self) -> bool:
        return registry.is_known(self.name)


@dataclass
class ParseError:
    reason: str
    raw: str = ""


class CommandParser:
    def parse(
        self,
        raw_text: str,
        username: str = "",
        fingerprint: str = "",
    ) -> ParsedCommand | ParseError | None:
        text = raw_text.strip()
        if not text.startswith(COMMAND_PREFIX):
            return None

        body = text[len(COMMAND_PREFIX) :].strip()
        if not body:
            return ParseError("Empty command. Try /help", raw=text)

        try:
            parts = shlex.split(body, posix=True)
        except ValueError:
            parts = body.split()

        if not parts:
            return ParseError("Empty command. Try /help", raw=text)

        invoked_as = re.sub(r"[^\w-].*$", "", parts[0].lower())
        canonical = registry.resolve(invoked_as)

        return ParsedCommand(
            raw=text,
            name=canonical,
            args=parts[1:],
            username=username,
            fingerprint=fingerprint,
            invoked_as=invoked_as,
        )
