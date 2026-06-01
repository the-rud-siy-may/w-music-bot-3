"""
Wakie UI element mapping for LDPlayer.

Uses confirmed Wakie resource IDs from LDPlayer UI inspection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class UIRegion:
    """A rectangular screen region (x, y, width, height) in device pixels."""

    x: int
    y: int
    width: int
    height: int

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    @classmethod
    def from_bounds(cls, left: int, top: int, right: int, bottom: int) -> UIRegion:
        return cls(x=left, y=top, width=right - left, height=bottom - top)


@dataclass
class UIMapper:
    """Central registry of Wakie UI selectors."""

    package: str = "com.wakie.android"

    # Confirmed Wakie resource IDs
    message_text_id: str = "com.wakie.android:id/text"
    username_id: str = "com.wakie.android:id/name"
    chat_input_id: str = "com.wakie.android:id/text_input"
    bubble_id: str = "com.wakie.android:id/bubble"
    chat_list_id: str = "android:id/list"
    list_container_id: str = "com.wakie.android:id/listContainer"
    input_container_id: str = "com.wakie.android:id/input_container"
    message_time_id: str = "com.wakie.android:id/message_time"
    fab_mic_id: str = "com.wakie.android:id/fab_mic"
    ab_title_id: str = "com.wakie.android:id/ab_title"
    tab_title_id: str = "com.wakie.android:id/tab_title"
    air_action_text_id: str = "com.wakie.android:id/air_action_text"
    air_action_button_id: str = "com.wakie.android:id/airActionButton"
    air_listener_layout_id: str = "com.wakie.android:id/airListenerLayout"

    # Send button candidates (may appear after typing)
    send_button_candidates: tuple[str, ...] = (
        "com.wakie.android:id/send",
        "com.wakie.android:id/send_button",
        "com.wakie.android:id/btn_send",
        "com.wakie.android:id/chat_send",
        "com.wakie.android:id/image_send",
        "com.wakie.android:id/send_icon",
        "com.wakie.android:id/iv_send",
        "com.wakie.android:id/action_send",
    )

    # Legacy placeholder
    send_button_id: str = "com.wakie.android:id/send"
    message_row_id: str = "com.wakie.android:id/message_row"
    timestamp_id: str = "com.wakie.android:id/message_time"

    chat_container_selectors: list[dict[str, str]] = field(default_factory=list)
    selectors: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.selectors:
            self.selectors = {
                "chat_list": f'//*[@resource-id="{self.chat_list_id}"]',
                "chat_input": f'//*[@resource-id="{self.chat_input_id}"]',
                "bubble": f'//*[@resource-id="{self.bubble_id}"]',
                "username": f'//*[@resource-id="{self.username_id}"]',
                "message_text": f'//*[@resource-id="{self.message_text_id}"]',
            }

        if not self.chat_container_selectors:
            self.chat_container_selectors = [
                {"resourceId": self.list_container_id},
                {"resourceId": self.chat_list_id},
                {"className": "androidx.recyclerview.widget.RecyclerView"},
            ]

    def get_selector(self, name: str) -> str | None:
        return self.selectors.get(name)

    def chat_row_xpaths(self) -> list[str]:
        return [
            f'//*[@resource-id="{self.bubble_id}"]',
            f'//*[@resource-id="{self.message_row_id}"]',
        ]

    @classmethod
    def from_package(cls, package: str) -> UIMapper:
        """Wakie IDs are fixed — package override only updates package field."""
        return cls(package=package)
