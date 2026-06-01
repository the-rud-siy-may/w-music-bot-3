"""
Persistent song queue manager.

Queue state is saved to storage/queue.json and restored on startup.
All mutating operations are async-safe via an internal lock.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import aiofiles

from utils.helpers import truncate
from utils.logger import get_logger

if TYPE_CHECKING:
    from config import BotConfig

logger = get_logger(__name__)


@dataclass
class QueueEntry:
    """A single item in the playback queue."""

    id: str
    title: str
    query: str
    requested_by: str = ""
    file_path: str | None = None
    duration_sec: float | None = None
    added_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_query(cls, query: str, requested_by: str = "", title: str | None = None) -> QueueEntry:
        """Create a new queue entry from a search query or URL."""
        return cls(
            id=str(uuid.uuid4())[:8],
            title=title or query,
            query=query,
            requested_by=requested_by,
        )

    @classmethod
    def from_dict(cls, data: dict) -> QueueEntry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class QueueState:
    """Serialisable snapshot of the full queue."""

    items: list[QueueEntry] = field(default_factory=list)
    current_id: str | None = None
    loop_enabled: bool = False
    version: int = 1


class QueueManager:
    """
    Thread/async-safe queue with JSON persistence.

    Supports add, remove, reorder, peek, pop, and loop toggle.
    """

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._path: Path = config.queue_file
        self._lock = asyncio.Lock()
        self._state = QueueState()
        logger.debug("QueueManager initialized → %s", self._path)

    # ── Persistence ────────────────────────────────────────────────────────

    async def load(self) -> None:
        """Load queue from disk; start fresh if file missing or corrupt."""
        async with self._lock:
            if not self._path.exists():
                logger.info("No queue file found; starting with empty queue")
                await self._save_unlocked()
                return

            try:
                async with aiofiles.open(self._path, "r", encoding="utf-8") as f:
                    raw = await f.read()
                data = json.loads(raw)
                items = [QueueEntry.from_dict(i) for i in data.get("items", [])]
                self._state = QueueState(
                    items=items,
                    current_id=data.get("current_id"),
                    loop_enabled=data.get("loop_enabled", False),
                    version=data.get("version", 1),
                )
                logger.info("Loaded queue: %d item(s)", len(self._state.items))
            except (json.JSONDecodeError, OSError, TypeError) as exc:
                logger.error("Failed to load queue (%s); resetting", exc)
                self._state = QueueState()
                await self._save_unlocked()

    async def save(self) -> None:
        """Persist current queue state to disk."""
        async with self._lock:
            await self._save_unlocked()

    async def _save_unlocked(self) -> None:
        payload = {
            "version": self._state.version,
            "current_id": self._state.current_id,
            "loop_enabled": self._state.loop_enabled,
            "items": [asdict(entry) for entry in self._state.items],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self._path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, indent=2, ensure_ascii=False))

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def length(self) -> int:
        return len(self._state.items)

    @property
    def current(self) -> QueueEntry | None:
        if self._state.current_id is None:
            return None
        return self._get_by_id(self._state.current_id)

    @property
    def loop_enabled(self) -> bool:
        return self._state.loop_enabled

    def _get_by_id(self, entry_id: str) -> QueueEntry | None:
        for item in self._state.items:
            if item.id == entry_id:
                return item
        return None

    def position_of(self, entry_id: str) -> int:
        """Return 1-based queue position, or 0 if not found."""
        for idx, item in enumerate(self._state.items, start=1):
            if item.id == entry_id:
                return idx
        return 0

    # ── Mutations ──────────────────────────────────────────────────────────

    async def add(
        self,
        query: str,
        requested_by: str = "",
        title: str | None = None,
        file_path: Path | str | None = None,
        front: bool = False,
        insert_after_current: bool = False,
    ) -> QueueEntry:
        """Add a song to the queue and persist."""
        entry = QueueEntry.from_query(query, requested_by=requested_by, title=title)
        if file_path is not None:
            entry.file_path = str(file_path)

        async with self._lock:
            if front:
                self._state.items.insert(0, entry)
            elif insert_after_current and self._state.current_id:
                idx = next(
                    (i for i, e in enumerate(self._state.items) if e.id == self._state.current_id),
                    -1,
                )
                self._state.items.insert(idx + 1, entry)
            else:
                self._state.items.append(entry)
            await self._save_unlocked()

        logger.info("Added to queue: %s (by %s)", entry.title, requested_by)
        return entry

    async def remove_at(self, position: int) -> QueueEntry | None:
        """Remove item at 1-based position."""
        async with self._lock:
            if not (1 <= position <= len(self._state.items)):
                return None
            removed = self._state.items.pop(position - 1)
            if removed.id == self._state.current_id:
                self._state.current_id = None
            await self._save_unlocked()
        logger.info("Removed from queue: %s", removed.title)
        return removed

    async def move(self, from_pos: int, to_pos: int) -> bool:
        """Move item from one 1-based position to another."""
        async with self._lock:
            n = len(self._state.items)
            if not (1 <= from_pos <= n and 1 <= to_pos <= n):
                return False
            item = self._state.items.pop(from_pos - 1)
            self._state.items.insert(to_pos - 1, item)
            await self._save_unlocked()
        return True

    async def clear(self) -> int:
        """Remove all items; return count cleared."""
        async with self._lock:
            count = len(self._state.items)
            self._state.items.clear()
            self._state.current_id = None
            await self._save_unlocked()
        logger.info("Queue cleared (%d items)", count)
        return count

    async def toggle_loop(self) -> bool:
        """Toggle loop mode; return new state."""
        async with self._lock:
            self._state.loop_enabled = not self._state.loop_enabled
            await self._save_unlocked()
        return self._state.loop_enabled

    async def set_current(self, entry: QueueEntry | None) -> None:
        """Mark an entry as currently playing."""
        async with self._lock:
            self._state.current_id = entry.id if entry else None
            await self._save_unlocked()

    async def consume_current(self) -> QueueEntry | None:
        """Remove the currently playing entry from the queue."""
        async with self._lock:
            if self._state.current_id is None:
                return None
            current = self._get_by_id(self._state.current_id)
            self._state.items = [i for i in self._state.items if i.id != self._state.current_id]
            self._state.current_id = None
            await self._save_unlocked()
            return current

    async def pop_next(self) -> QueueEntry | None:
        """
        Return and remove the next track to play.

        Skips the current track if it is still at the head.
        """
        async with self._lock:
            if not self._state.items:
                return None

            # Find first item that isn't the current playing track
            for idx, item in enumerate(self._state.items):
                if item.id != self._state.current_id:
                    nxt = self._state.items.pop(idx)
                    self._state.current_id = nxt.id
                    await self._save_unlocked()
                    return nxt

            # Only current track remains — pop it if loop is off
            if not self._state.loop_enabled:
                nxt = self._state.items.pop(0)
                self._state.current_id = nxt.id
                await self._save_unlocked()
                return nxt

            return self._state.items[0] if self._state.items else None

    def peek_next(self) -> QueueEntry | None:
        """Return next track without removing it."""
        for item in self._state.items:
            if item.id != self._state.current_id:
                return item
        return self._state.items[0] if self._state.items else None

    def format_listing(self, max_items: int = 15) -> str:
        """Format queue as a numbered chat-friendly string."""
        if not self._state.items:
            return ""
        lines: list[str] = []
        for idx, item in enumerate(self._state.items[:max_items], start=1):
            marker = " ▶" if item.id == self._state.current_id else ""
            lines.append(f"{idx}. {truncate(item.title, 60)}{marker}")
        if len(self._state.items) > max_items:
            lines.append(f"… and {len(self._state.items) - max_items} more")
        return "\n".join(lines)
