"""
Async-safe stream queue with user-priority over autoplay tracks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from player.models import QueueEntry
from utils.helpers import normalize_username, truncate
from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig
    from player.autoplay_manager import AutoplayManager

logger = get_logger(__name__)


class StreamQueueManager:
    """Dual-queue manager: user requests first, autoplay second."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._lock = asyncio.Lock()
        self._user: list[QueueEntry] = []
        self._autoplay: list[QueueEntry] = []
        self._current_id: str | None = None
        self._autoplay_mgr: AutoplayManager | None = None

    def bind_autoplay(self, manager: AutoplayManager) -> None:
        self._autoplay_mgr = manager

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def length(self) -> int:
        return len(self._user) + len(self._autoplay)

    @property
    def user_length(self) -> int:
        return len(self._user)

    @property
    def current(self) -> QueueEntry | None:
        if self._current_id is None:
            return None
        return self._get_by_id(self._current_id)

    def position_of(self, entry_id: str) -> int:
        for idx, item in enumerate(self._all_items(), start=1):
            if item.id == entry_id:
                return idx
        return 0

    def _all_items(self) -> list[QueueEntry]:
        return self._user + self._autoplay

    def _get_by_id(self, entry_id: str) -> QueueEntry | None:
        for item in self._all_items():
            if item.id == entry_id:
                return item
        return None

    # ── Mutations ──────────────────────────────────────────────────────────

    async def add_user(
        self,
        entry: QueueEntry,
        *,
        front: bool = False,
        insert_after_current: bool = False,
    ) -> QueueEntry:
        """Add a user-requested track; pauses autoplay priority."""
        entry.source = "user"
        async with self._lock:
            if front:
                self._user.insert(0, entry)
            elif insert_after_current and self._current_id:
                idx = next((i for i, e in enumerate(self._user) if e.id == self._current_id), -1)
                if idx >= 0:
                    self._user.insert(idx + 1, entry)
                else:
                    self._user.append(entry)
            else:
                self._user.append(entry)

        if self._autoplay_mgr:
            self._autoplay_mgr.pause_for_user()

        logger.info("User queued: %s (#%d)", entry.title, self.position_of(entry.id))
        return entry

    async def add(
        self,
        query: str,
        requested_by: str = "",
        title: str | None = None,
        file_path: Path | str | None = None,
        front: bool = False,
        insert_after_current: bool = False,
        **kwargs,
    ) -> QueueEntry:
        """Legacy add — prefer add_user() with a built QueueEntry."""
        entry = QueueEntry.create(
            title=title or query,
            query=query,
            requested_by=requested_by,
            file_path=str(file_path) if file_path else None,
            stream_url=kwargs.get("stream_url", ""),
            youtube_url=kwargs.get("youtube_url", ""),
        )
        return await self.add_user(entry, front=front, insert_after_current=insert_after_current)

    async def add_autoplay(self, entry: QueueEntry) -> QueueEntry:
        entry.source = "autoplay"
        async with self._lock:
            self._autoplay.append(entry)
        logger.info("Autoplay queued: %s", entry.title)
        return entry

    async def remove_at(
        self,
        position: int,
        *,
        username: str = "",
        is_moderator: bool = False,
    ) -> tuple[QueueEntry | None, str]:
        """Remove by queue position; enforce requester ownership unless moderator."""
        async with self._lock:
            items = self._all_items()
            if not (1 <= position <= len(items)):
                return None, f"No item at position {position}."

            target = items[position - 1]
            ok, reason = self._can_modify_entry(target, username, is_moderator)
            if not ok:
                return None, reason

            if target in self._user:
                self._user.remove(target)
            else:
                self._autoplay.remove(target)
            if target.id == self._current_id:
                self._current_id = None
        return target, ""

    def can_skip_current(self, username: str, *, is_moderator: bool = False) -> tuple[bool, str]:
        current = self.current
        if current is None:
            return False, "Nothing playing to skip."
        return self._can_modify_entry(current, username, is_moderator)

    def _can_modify_entry(
        self,
        entry: QueueEntry,
        username: str,
        is_moderator: bool,
    ) -> tuple[bool, str]:
        if is_moderator:
            return True, ""
        if entry.source == "autoplay":
            return False, "You can only skip or remove songs you added."
        owner = normalize_username(entry.requested_by or "")
        user = normalize_username(username)
        if not owner or owner != user:
            return False, "You can only skip or remove songs you added."
        return True, ""

    async def clear_for_user(self, username: str, *, is_moderator: bool = False) -> int:
        """Clear queue items — moderators clear all user requests; others clear only their own."""
        async with self._lock:
            if is_moderator:
                count = len(self._user)
                self._user.clear()
            else:
                user_norm = normalize_username(username)
                before = len(self._user)
                self._user = [
                    e for e in self._user
                    if normalize_username(e.requested_by or "") != user_norm
                ]
                count = before - len(self._user)
            if self._current_id and self._get_by_id(self._current_id) is None:
                self._current_id = None
        return count

    async def move(self, from_pos: int, to_pos: int) -> bool:
        async with self._lock:
            items = self._all_items()
            n = len(items)
            if not (1 <= from_pos <= n and 1 <= to_pos <= n):
                return False
            item = items.pop(from_pos - 1)
            items.insert(to_pos - 1, item)
            self._user = [i for i in items if i.source == "user"]
            self._autoplay = [i for i in items if i.source == "autoplay"]
        return True

    async def clear_user(self) -> int:
        async with self._lock:
            count = len(self._user)
            self._user.clear()
            if self._current_id and self._get_by_id(self._current_id) is None:
                self._current_id = None
        return count

    async def clear(self) -> int:
        async with self._lock:
            count = len(self._user) + len(self._autoplay)
            self._user.clear()
            self._autoplay.clear()
            self._current_id = None
        return count

    async def toggle_loop(self) -> bool:
        return False

    async def set_current(self, entry: QueueEntry | None) -> None:
        async with self._lock:
            self._current_id = entry.id if entry else None

    async def consume_current(self) -> QueueEntry | None:
        async with self._lock:
            if self._current_id is None:
                return None
            current = self._get_by_id(self._current_id)
            if current in self._user:
                self._user.remove(current)
            elif current in self._autoplay:
                self._autoplay.remove(current)
            self._current_id = None
            return current

    async def pop_next(self) -> QueueEntry | None:
        """Pop next track — user queue first, then autoplay."""
        async with self._lock:
            nxt = self._pop_from_list(self._user)
            if nxt is None:
                nxt = self._pop_from_list(self._autoplay)
            if nxt is not None:
                self._current_id = nxt.id
            return nxt

    def _pop_from_list(self, items: list[QueueEntry]) -> QueueEntry | None:
        for idx, item in enumerate(items):
            if item.id != self._current_id:
                return items.pop(idx)
        if items and items[0].id == self._current_id:
            return items.pop(0)
        return items.pop(0) if items else None

    def peek_next(self) -> QueueEntry | None:
        for item in self._user + self._autoplay:
            if item.id != self._current_id:
                return item
        combined = self._user + self._autoplay
        return combined[0] if combined else None

    def format_listing(self, max_items: int = 15) -> str:
        items = self._all_items()
        if not items:
            return ""
        lines: list[str] = []
        for idx, item in enumerate(items[:max_items], start=1):
            marker = " ▶" if item.id == self._current_id else ""
            tag = " [autoplay]" if item.source == "autoplay" else ""
            lines.append(f"{idx}. {truncate(item.title, 55)}{tag}{marker}")
        if len(items) > max_items:
            lines.append(f"… and {len(items) - max_items} more")
        return "\n".join(lines)

    async def ensure_autoplay_track(self) -> QueueEntry | None:
        """Fetch next autoplay entry when both queues are empty."""
        if self._autoplay_mgr is None or self._autoplay_mgr.paused_for_user:
            return None
        if self.length > 0:
            return None
        entry = await self._autoplay_mgr.next_entry()
        if entry:
            await self.add_autoplay(entry)
        return entry

    def was_empty_before_user_add(self) -> bool:
        """True when idle — no user tracks and nothing marked current."""
        return self.user_length == 0 and self._current_id is None

    async def on_user_queue_drained(self) -> bool:
        """Called when user queue becomes empty — resume autoplay."""
        if self._autoplay_mgr and self.user_length == 0:
            return self._autoplay_mgr.resume_if_allowed()
        return False

    async def load(self) -> None:
        pass

    async def save(self) -> None:
        pass
