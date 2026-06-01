"""Random fun bot responses."""

from __future__ import annotations

import random

SIYA_REPLY = "Siya is my gf i love her a lot 💕"

GREET_REPLIES = (
    "Hey {user}! 🎵 Drop a /add and let's vibe.",
    "Yo {user}! The aux cord is yours — try /add <song>",
    "{user} entered the chat. DJ mode: activated 🎧",
)

ADD_REPLIES = (
    "Solid pick. Queue updated 🎶",
    "Added! Hope the club is ready for this one 🔥",
)

SKIP_REPLIES = (
    "Skipped. Next banger loading… ⏭️",
    "Gone. Something better is coming 🎵",
)

FUN_COMMAND_REPLIES = (
    "🎉 You found the fun button!",
    "✨ Bot go brrr",
    "🤖 Beep boop — music machine online",
    "🎸 Rock on!",
)


def pick_greet(username: str) -> str:
    return random.choice(GREET_REPLIES).format(user=username)


def pick_add_extra() -> str:
    return random.choice(ADD_REPLIES)


def pick_skip_extra() -> str:
    return random.choice(SKIP_REPLIES)


def pick_fun() -> str:
    return random.choice(FUN_COMMAND_REPLIES)
