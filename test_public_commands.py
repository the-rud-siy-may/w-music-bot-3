"""
Smoke-test public command handlers (no VLC / Wakie device).
Run: python test_public_commands.py
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from commands.parser import ParsedCommand
from commands.public_commands import PublicCommands
from commands.registry import registry
from config import load_config
from player.models import QueueEntry
from player.stream_queue import StreamQueueManager
from utils.constants import COMMAND_REGISTRY, CommandTier


def _cmd(name: str, *args: str, username: str = "tester") -> ParsedCommand:
    return ParsedCommand(raw=f"/{name}", name=name, args=list(args), username=username)


async def main() -> None:
    config = load_config()
    queue = StreamQueueManager(config)
    player = MagicMock()
    player.current_track = None
    player.state_label = "idle"
    player.stop = AsyncMock()

    volume = MagicMock()
    volume.current = 80

    permissions = MagicMock()
    permissions.is_moderator = MagicMock(return_value=False)
    permissions.tier_for_user = MagicMock(return_value=CommandTier.PUBLIC)

    youtube = AsyncMock()
    youtube.extract_stream = AsyncMock(
        return_value={
            "title": "Test Song",
            "stream_url": "http://example.com/stream",
            "youtube_url": "http://youtube.com/watch?v=1",
            "duration": 120,
            "query": "test",
        }
    )

    autoplay = MagicMock()
    autoplay.is_active = False

    ctx = MagicMock()
    ctx.config = config
    ctx.queue = queue
    ctx.player = player
    ctx.volume = volume
    ctx.permissions = permissions
    ctx.youtube = youtube
    ctx.autoplay = autoplay
    ctx.downloader = MagicMock()

    pub = PublicCommands(ctx)
    errors: list[str] = []

    # Registry ↔ handler coverage
    public_names = {s.name for s in COMMAND_REGISTRY.values() if s.tier == CommandTier.PUBLIC}
    handler_names = set(pub.handlers.keys())
    missing = public_names - handler_names
    extra = handler_names - public_names
    if missing:
        errors.append(f"Missing handlers: {missing}")
    if extra:
        errors.append(f"Extra handlers not in registry: {extra}")

    # /help
    r = await pub.cmd_help(_cmd("help"))
    assert r.success and "Public (everyone)" in r.message, r.message

    # /greet
    r = await pub.cmd_greet(_cmd("greet", username="Alice"))
    assert r.success and "Alice" in r.message

    # /volume /status empty
    r = await pub.cmd_volume(_cmd("volume"))
    assert r.success and "80" in r.message
    r = await pub.cmd_status(_cmd("status"))
    assert r.success

    # /add no args
    r = await pub.cmd_add(_cmd("add"))
    assert not r.success and "Usage" in r.message

    # /add youtube
    r = await pub.cmd_add(_cmd("add", "test song"))
    assert r.success and "Added" in r.message, r.message
    assert queue.user_length == 1

    # /q with waiting item
    r = await pub.cmd_q(_cmd("q"))
    assert r.success and "Test Song" in r.message, r.message

    # Simulate now playing (popped from waiting queue)
    entry = queue._user[0]
    await queue.pop_next()
    assert queue.current is entry
    assert queue.length == 0

    r = await pub.cmd_np(_cmd("np"))
    assert r.success and "Test Song" in r.message, r.message

    r = await pub.cmd_q(_cmd("q"))
    if "Now" not in r.message and "▶" not in r.message:
        errors.append(f"/q should show now playing when idle queue but song active: {r.message!r}")

    r = await pub.cmd_upnext(_cmd("upnext"))
    assert r.success  # empty next is ok

    # /skip
    player.current_track = entry
    r = await pub.cmd_skip(_cmd("skip"))
    assert r.success and "Skipped" in r.message, r.message
    player.stop.assert_awaited()
    assert queue.current is None

    # /remove ownership
    e2 = QueueEntry.create(title="Other", query="x", requested_by="other")
    await queue.add_user(e2)
    r = await pub.cmd_remove(_cmd("remove", "1", username="tester"))
    assert not r.success and "only" in r.message.lower()

    r = await pub.cmd_remove(_cmd("remove", "1", username="other"))
    assert r.success

    # /clear
    e3 = QueueEntry.create(title="Mine", query="y", requested_by="tester")
    await queue.add_user(e3)
    r = await pub.cmd_clear(_cmd("clear", username="tester"))
    assert r.success and "1" in r.message

    # Aliases resolve
    for alias in ("queue", "sk", "nowplaying", "h"):
        canonical = registry.resolve(alias)
        assert registry.get(canonical) is not None, alias

    if errors:
        print("FAILED:")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit(1)

    print("All public command smoke tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
