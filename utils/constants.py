"""
Command registry — name, tier, description, aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class CommandTier(Enum):
    PUBLIC = auto()
    DELEGATED = auto()
    OWNER = auto()


@dataclass(frozen=True)
class CommandSpec:
    name: str
    tier: CommandTier
    description: str
    usage: str
    aliases: tuple[str, ...] = ()
    cooldown: float | None = None


COMMAND_REGISTRY: dict[str, CommandSpec] = {
    "add": CommandSpec("add", CommandTier.PUBLIC, "Add song to queue.", "/add <song|url>", ("a", "enqueue")),
    "q": CommandSpec("q", CommandTier.PUBLIC, "Show queue.", "/q", ("queue", "list")),
    "upnext": CommandSpec("upnext", CommandTier.PUBLIC, "Next song.", "/upnext"),
    "remove": CommandSpec("remove", CommandTier.PUBLIC, "Remove by number.", "/remove <n>", ("rm", "del")),
    "skip": CommandSpec("skip", CommandTier.PUBLIC, "Skip current song.", "/skip", ("sk", "next")),
    "clear": CommandSpec("clear", CommandTier.PUBLIC, "Clear queue requests.", "/clear", ("clr",)),
    "np": CommandSpec("np", CommandTier.PUBLIC, "Now playing.", "/np", ("nowplaying", "now")),
    "volume": CommandSpec("volume", CommandTier.PUBLIC, "Show volume.", "/volume"),
    "status": CommandSpec("status", CommandTier.PUBLIC, "Bot status.", "/status", ("info",)),
    "greet": CommandSpec("greet", CommandTier.PUBLIC, "Greeting.", "/greet", ("hi", "hello")),
    "help": CommandSpec("help", CommandTier.PUBLIC, "Command list.", "/help", ("h", "commands"), cooldown=0),
    "pause": CommandSpec("pause", CommandTier.DELEGATED, "Pause playback.", "/pause"),
    "resume": CommandSpec("resume", CommandTier.DELEGATED, "Resume playback.", "/resume", ("unpause",)),
    "stop": CommandSpec("stop", CommandTier.DELEGATED, "Stop playback.", "/stop"),
    "vol": CommandSpec("vol", CommandTier.DELEGATED, "Set volume 0–200.", "/vol <n>"),
    "loop": CommandSpec("loop", CommandTier.DELEGATED, "Toggle loop.", "/loop"),
    "play": CommandSpec("play", CommandTier.OWNER, "Play now.", "/play [song|url]"),
    "addnext": CommandSpec("addnext", CommandTier.OWNER, "Insert after current.", "/addnext <song|url>"),
    "move": CommandSpec("move", CommandTier.OWNER, "Reorder queue.", "/move <from> <to>"),
    "topic": CommandSpec("topic", CommandTier.OWNER, "Set topic.", "/topic [text]"),
    "restart": CommandSpec("restart", CommandTier.OWNER, "Restart bot.", "/restart", cooldown=0),
    "lock": CommandSpec("lock", CommandTier.OWNER, "Lock public commands.", "/lock"),
    "unlock": CommandSpec("unlock", CommandTier.OWNER, "Unlock public commands.", "/unlock"),
    "mute": CommandSpec("mute", CommandTier.OWNER, "Mute bot replies.", "/mute"),
    "unmute": CommandSpec("unmute", CommandTier.OWNER, "Unmute bot replies.", "/unmute"),
    "block": CommandSpec("block", CommandTier.OWNER, "Block user.", "/block <user>"),
    "unblock": CommandSpec("unblock", CommandTier.OWNER, "Unblock user.", "/unblock <user>"),
    "clearcache": CommandSpec("clearcache", CommandTier.OWNER, "Clear cache.", "/clearcache"),
}

COMMAND_PREFIX = "/"

TIER_ORDER: dict[CommandTier, int] = {
    CommandTier.PUBLIC: 0,
    CommandTier.DELEGATED: 1,
    CommandTier.OWNER: 2,
}
