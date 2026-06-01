"""Backward-compatible re-exports — use player.models / player.stream_queue."""

from player.models import QueueEntry
from player.stream_queue import StreamQueueManager as MemoryQueueManager

__all__ = ["QueueEntry", "MemoryQueueManager"]
