"""
Wakie-specific chat extraction using known resource IDs.

Pairs username (id/name) and message (id/text) inside each chat bubble.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from utils.logger import get_logger
from utils.helpers import normalize_command_text
from wakie.reader import ChatMessage, _content_fingerprint, _parse_bounds as parse_bounds

if TYPE_CHECKING:
    from wakie.ui_mapper import UIMapper

logger = get_logger(__name__)

# Masked / placeholder usernames in Wakie UI
_MASKED_NAME_RE = re.compile(r"^\.+$")


class WakieChatExtractor:
    """Read chat messages from Wakie voice-chat UI via uiautomator2."""

    def __init__(self, ui: UIMapper) -> None:
        self._ui = ui

    def extract(self, device: Any) -> list[ChatMessage]:
        """
        Extract messages from visible chat bubbles.

        Each bubble (resource-id=bubble) contains:
          - com.wakie.android:id/name  (optional)
          - com.wakie.android:id/text  (message body)
        """
        messages: list[ChatMessage] = []

        try:
            bubbles = device.xpath(f'//*[@resource-id="{self._ui.bubble_id}"]').all()
        except Exception as exc:
            logger.warning("Bubble xpath failed: %s", exc)
            bubbles = []

        if bubbles:
            for bubble in bubbles:
                msg = self._parse_bubble(bubble)
                if msg is not None:
                    messages.append(msg)
        else:
            # Fallback: pair global name + text nodes by vertical position
            messages = self._extract_by_pairing(device)

        logger.debug("WakieChatExtractor: %d message(s)", len(messages))
        return messages

    def _parse_bubble(self, bubble: Any) -> ChatMessage | None:
        try:
            info = bubble.info
        except Exception:
            return None

        username = ""
        message = ""
        bubble_bounds = parse_bounds(info.get("bounds"))
        bounds_anchor = str(info.get("bounds", ""))

        try:
            name_el = bubble.child(resourceId=self._ui.username_id)
            if name_el.exists(timeout=0):
                username = (name_el.info.get("text") or "").strip()
        except Exception:
            pass

        try:
            text_el = bubble.child(resourceId=self._ui.message_text_id)
            if text_el.exists(timeout=0):
                message = (text_el.info.get("text") or "").strip()
                bounds_anchor += str(text_el.info.get("bounds", ""))
        except Exception:
            pass

        if not message:
            return None

        if not username or _MASKED_NAME_RE.match(username):
            username = "unknown"

        if message.strip().startswith("/"):
            msg_id = _content_fingerprint("cmd", normalize_command_text(message), "")
        else:
            msg_id = _content_fingerprint(username, message, bounds_anchor)

        return ChatMessage(
            username=username,
            message=message,
            timestamp=datetime.now(timezone.utc),
            message_id=msg_id,
            source="ui",
            bubble_bounds=bubble_bounds,
        )

    def _extract_by_pairing(self, device: Any) -> list[ChatMessage]:
        """Fallback when bubble nodes are not found — pair name/text by Y position."""
        names = self._collect_nodes(device, self._ui.username_id)
        texts = self._collect_nodes(device, self._ui.message_text_id)

        # Filter out header "You" name above chat list (y < 400 on 1600p)
        names = [n for n in names if n["top"] > 400]
        texts = [t for t in texts if t["top"] > 400 and t["text"]]

        messages: list[ChatMessage] = []
        used_names: set[int] = set()

        for text_node in sorted(texts, key=lambda n: n["top"]):
            best_name = "unknown"
            best_idx = -1
            for idx, name_node in enumerate(names):
                if idx in used_names:
                    continue
                if name_node["top"] <= text_node["top"] and text_node["top"] - name_node["top"] < 120:
                    best_name = name_node["text"]
                    best_idx = idx
                    break

            if best_idx >= 0:
                used_names.add(best_idx)

            if _MASKED_NAME_RE.match(best_name):
                best_name = "unknown"

            text = text_node["text"]
            if text.strip().startswith("/"):
                msg_id = _content_fingerprint("cmd", normalize_command_text(text), "")
            else:
                msg_id = _content_fingerprint(best_name, text, f"{text_node['bounds']}")

            messages.append(
                ChatMessage(
                    username=best_name,
                    message=text,
                    timestamp=datetime.now(timezone.utc),
                    message_id=msg_id,
                    source="ui",
                    bubble_bounds=text_node.get("bounds"),
                )
            )

        return messages

    def _collect_nodes(self, device: Any, resource_id: str) -> list[dict]:
        nodes: list[dict] = []
        try:
            elements = device(resourceId=resource_id).all()
        except Exception:
            return nodes

        for el in elements:
            try:
                info = el.info
                text = (info.get("text") or "").strip()
                bounds = parse_bounds(info.get("bounds"))
                if bounds is None:
                    continue
                left, top, right, bottom = bounds
                nodes.append({"text": text, "top": top, "bounds": bounds, "left": left})
            except Exception:
                continue
        return nodes
