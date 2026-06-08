"""
Command registry — specs, aliases, help text.
"""

from __future__ import annotations

from utils.constants import COMMAND_PREFIX, COMMAND_REGISTRY, CommandSpec, CommandTier, TIER_ORDER
from utils.logger import get_logger

logger = get_logger(__name__)


class CommandRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, CommandSpec] = dict(COMMAND_REGISTRY)
        self._aliases: dict[str, str] = {}
        for spec in self._specs.values():
            for alias in spec.aliases:
                self._aliases[alias.lower()] = spec.name

    def resolve(self, name: str) -> str:
        key = name.lower().strip()
        return self._aliases.get(key, key if key in self._specs else key)

    def get(self, name: str) -> CommandSpec | None:
        return self._specs.get(self.resolve(name))

    def is_known(self, name: str) -> bool:
        return self.get(name) is not None

    def specs_for_tier(self, max_tier: CommandTier) -> list[CommandSpec]:
        return [s for s in self._specs.values() if TIER_ORDER[s.tier] <= TIER_ORDER[max_tier]]

    def help_text(self, max_tier: CommandTier) -> str:
        tier_sections: list[tuple[CommandTier, str]] = [
            (CommandTier.PUBLIC, "Public (everyone)"),
            (CommandTier.DELEGATED, "Admin (mods)"),
            (CommandTier.OWNER, "Owner"),
        ]
        lines = ["Music bot — commands", ""]
        first = True
        for tier, heading in tier_sections:
            if TIER_ORDER[tier] > TIER_ORDER[max_tier]:
                continue
            specs = sorted(
                (s for s in self._specs.values() if s.tier == tier),
                key=lambda s: s.name,
            )
            if not specs:
                continue
            if not first:
                lines.append("")
            lines.append(f"{heading}:")
            for spec in specs:
                lines.append(f"  {spec.usage} — {spec.description}")
            first = False
        return "\n".join(lines)

    def unknown_command_message(self, invoked_name: str) -> str:
        return f"Unknown command: {COMMAND_PREFIX}{invoked_name}. Try {COMMAND_PREFIX}help"


registry = CommandRegistry()
