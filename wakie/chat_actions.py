"""
Wakie chat UI — tap a message, open Reply, send threaded response.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

from utils.logger import get_logger
from wakie.chat import _try_send_once
from wakie.reader import _parse_bounds
from wakie.send_finder import SendButtonFinder

if TYPE_CHECKING:
    from wakie.reader import ChatMessage
    from wakie.ui_mapper import UIMapper

logger = get_logger(__name__)

_REPLY_LABELS = ("reply", "ответ")
_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def send_reply_to_message(
    device: Any,
    ui: UIMapper,
    text: str,
    reply_to: ChatMessage,
    *,
    post_type_delay: float = 0.45,
    safe_send_only: bool = False,
) -> bool:
    """Tap the user's message → Reply → type and send."""
    if not text or not text.strip():
        return False

    if not _open_reply_target(device, ui, reply_to):
        logger.warning(
            "Could not open reply menu for message %r",
            reply_to.message[:80],
        )
        return False

    time.sleep(0.2)
    finder = SendButtonFinder(ui)
    if _try_send_once(device, text, ui, finder, post_type_delay, safe_send_only):
        logger.info("Reply sent to %s", reply_to.message[:60])
        return True

    logger.warning("Reply typed but send failed for %r", reply_to.message[:60])
    return False


def _open_reply_target(device: Any, ui: UIMapper, msg: ChatMessage) -> bool:
    bounds = _resolve_message_bounds(device, ui, msg)
    if bounds is None:
        return False

    cx, cy = _center(bounds)
    device.click(cx, cy)
    time.sleep(0.45)

    if _tap_reply_menu(device):
        return True

    device.long_click(cx, cy, duration=0.9)
    time.sleep(0.5)
    return _tap_reply_menu(device)


def _resolve_message_bounds(
    device: Any,
    ui: UIMapper,
    msg: ChatMessage,
) -> tuple[int, int, int, int] | None:
    if msg.bubble_bounds:
        return msg.bubble_bounds

    needle = _normalize_match_text(msg.message)
    if not needle:
        return None

    try:
        bubbles = device.xpath(f'//*[@resource-id="{ui.bubble_id}"]').all()
    except Exception as exc:
        logger.debug("Bubble search failed: %s", exc)
        bubbles = []

    best: tuple[int, tuple[int, int, int, int]] | None = None
    for bubble in bubbles:
        try:
            text_el = bubble.child(resourceId=ui.message_text_id)
            if not text_el.exists(timeout=0):
                continue
            bubble_text = (text_el.info.get("text") or "").strip()
            if not bubble_text:
                continue
            score = _match_score(needle, _normalize_match_text(bubble_text))
            if score <= 0:
                continue
            bounds = _parse_bounds(text_el.info.get("bounds")) or _parse_bounds(bubble.info.get("bounds"))
            if bounds and (best is None or score > best[0]):
                best = (score, bounds)
        except Exception:
            continue

    if best:
        return best[1]

    try:
        texts = device(resourceId=ui.message_text_id)
        if not texts.exists(timeout=0):
            return None
        count = texts.count if hasattr(texts, "count") else 1
        for i in range(min(count, 40)):
            try:
                el = texts[i] if count > 1 else texts
                bubble_text = (el.info.get("text") or "").strip()
                score = _match_score(needle, _normalize_match_text(bubble_text))
                if score <= 0:
                    continue
                bounds = _parse_bounds(el.info.get("bounds"))
                if bounds:
                    return bounds
            except Exception:
                continue
    except Exception as exc:
        logger.debug("Text node search failed: %s", exc)

    return None


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _match_score(needle: str, haystack: str) -> int:
    if not needle or not haystack:
        return 0
    if needle == haystack:
        return 100
    if haystack.startswith(needle) or needle.startswith(haystack):
        return 80
    if needle in haystack or haystack in needle:
        return 60
    return 0


def _tap_reply_menu(device: Any) -> bool:
    for label in _REPLY_LABELS:
        try:
            el = device(textMatches=f"(?i).*{label}.*")
            if el.exists(timeout=0.8):
                el.click()
                time.sleep(0.25)
                logger.debug("Tapped reply menu: %s", label)
                return True
        except Exception:
            pass

        try:
            el = device(textContains=label.capitalize())
            if el.exists(timeout=0.5):
                el.click()
                time.sleep(0.25)
                return True
        except Exception:
            pass

    try:
        matches = device.xpath('//*[contains(translate(@text,"REPLY","reply"),"reply")]').all()
        for el in matches:
            try:
                if el.exists(timeout=0):
                    el.click()
                    time.sleep(0.25)
                    return True
            except Exception:
                continue
    except Exception:
        pass

    return False


def _center(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = bounds
    return (left + right) // 2, (top + bottom) // 2
