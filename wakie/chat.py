"""
Wakie chat helpers — type and send messages into voice-chat.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, TYPE_CHECKING

from utils.logger import get_logger
from wakie.send_finder import SendButtonFinder, SendTarget

if TYPE_CHECKING:
    from wakie.ui_mapper import UIMapper

logger = get_logger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_POST_TYPE_DELAY = 0.45
DEFAULT_RETRY_DELAY = 0.6

INPUT_HINTS = ("type your message", "type a message")


def send_chat_message(
    device: Any,
    text: str,
    ui: UIMapper,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    post_type_delay: float = DEFAULT_POST_TYPE_DELAY,
    safe_send_only: bool = False,
) -> bool:
    """
    Type a message into Wakie chat and submit it automatically.

    Strategy order (per attempt):
      1. Type into text_input
      2. Click detected send button (resource-id / content-desc / hierarchy)
      3. IME editor action / Enter
      4. Coordinate tap on right side of input bar
      5. ADB KEYCODE_ENTER keyevent

    Returns True when the input field clears after send.
    """
    if not text or not text.strip():
        logger.warning("send_chat_message: empty text")
        return False

    finder = SendButtonFinder(ui)
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        try:
            if _try_send_once(device, text, ui, finder, post_type_delay, safe_send_only):
                logger.info("Message sent")
                return True
            last_error = "send verification failed (input not cleared)"
        except Exception as exc:
            last_error = str(exc)
            logger.warning("Send attempt %d/%d error: %s", attempt, max_attempts, exc)

        if attempt < max_attempts:
            logger.info("Retrying send (%d/%d)…", attempt + 1, max_attempts)
            time.sleep(DEFAULT_RETRY_DELAY)

    logger.error("send_chat_message failed after %d attempts: %s", max_attempts, last_error)
    return False


def _try_send_once(
    device: Any,
    text: str,
    ui: UIMapper,
    finder: SendButtonFinder,
    post_type_delay: float,
    safe_send_only: bool = False,
) -> bool:
    """Single send attempt with cascading fallbacks."""
    input_el = device(resourceId=ui.chat_input_id)
    if not input_el.exists(timeout=3):
        raise RuntimeError(f"Chat input not found: {ui.chat_input_id}")

    # Prefer fast input IME for reliability on emulators
    try:
        device.set_fastinput_ime(True)
    except Exception:
        pass

    input_el.click()
    time.sleep(0.15)

    # Clear placeholder / prior text then type
    try:
        input_el.clear_text()
    except Exception:
        pass

    input_el.set_text(text)
    logger.info("Message typed")

    time.sleep(post_type_delay)

    # ── Try detected send buttons (resource-id only when safe mode) ────────
    targets = finder.find(device, safe_only=safe_send_only)
    for target in targets:
        if _click_send_target(device, target):
            logger.info("Send button clicked (%s: %s)", target.method, target.detail)
            time.sleep(0.35)
            if _verify_sent(device, ui, text):
                return True

    if safe_send_only:
        return False

    # ── Fallback: IME / Enter (disabled in safe mode — can leave club) ─────
    if _try_editor_action(device, input_el):
        logger.info("Send button clicked (ime: editor_action)")
        time.sleep(0.35)
        if _verify_sent(device, ui, text):
            return True

    if _try_keyevent(device, "enter"):
        logger.info("Send button clicked (keyevent: enter)")
        time.sleep(0.35)
        if _verify_sent(device, ui, text):
            return True

    # ── Fallback: coordinate tap ───────────────────────────────────────────
    coord = finder.coordinate_fallback(device)
    if coord and coord.bounds:
        cx, cy = (coord.bounds[0] + coord.bounds[2]) // 2, (coord.bounds[1] + coord.bounds[3]) // 2
        device.click(cx, cy)
        logger.info("Send button clicked (coordinate: %s)", coord.detail)
        time.sleep(0.35)
        if _verify_sent(device, ui, text):
            return True

    if _try_adb_keyevent(device, 66):
        logger.info("Send button clicked (keyevent: adb_66)")
        time.sleep(0.35)
        if _verify_sent(device, ui, text):
            return True

    return False


def _click_send_target(device: Any, target: SendTarget) -> bool:
    try:
        if target.element is not None:
            target.element.click()
            return True
        if target.method in ("resource_id", "hierarchy") and ":id/" in target.detail:
            el = device(resourceId=target.detail)
            if el.exists(timeout=0.5):
                el.click()
                return True
        if target.bounds:
            cx, cy = _center(target.bounds)
            device.click(cx, cy)
            return True
    except Exception as exc:
        logger.debug("Click send target failed (%s): %s", target.detail, exc)
    return False


def _center(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = bounds
    return (left + right) // 2, (top + bottom) // 2


def _try_editor_action(device: Any, input_el: Any) -> bool:
    """Trigger keyboard IME send action."""
    try:
        input_el.click()
        # uiautomator2 editor action codes: 4 = IME_ACTION_SEND on some devices
        if hasattr(device, "press"):
            device.press("enter")
            return True
    except Exception as exc:
        logger.debug("Editor action failed: %s", exc)
    return False


def _try_keyevent(device: Any, key: str) -> bool:
    try:
        device.press(key)
        return True
    except Exception as exc:
        logger.debug("press(%s) failed: %s", key, exc)
    return False


def _try_adb_keyevent(device: Any, code: int) -> bool:
    try:
        device.shell(f"input keyevent {code}")
        return True
    except Exception as exc:
        logger.debug("adb keyevent %d failed: %s", code, exc)
    return False


def _verify_sent(device: Any, ui: UIMapper, sent_text: str) -> bool:
    """
    Verify message was sent.

    Heuristic: input field is empty or shows placeholder again.
    """
    try:
        input_el = device(resourceId=ui.chat_input_id)
        if not input_el.exists(timeout=1):
            return True

        current = (input_el.get_text() or input_el.info.get("text") or "").strip()
        hint = (input_el.info.get("hint") or "").strip().lower()

        if not current:
            return True
        if current.lower() in INPUT_HINTS:
            return True
        if hint and current.lower() == hint:
            return True
        # Partial clear — Wakie may truncate; not equal to full sent text
        if sent_text and current != sent_text.strip():
            return True

        logger.debug("Input still contains: %r", current[:60])
    except Exception as exc:
        logger.debug("Send verify error: %s", exc)
        return True  # assume sent if we cannot read field
    return False


async def send_chat_message_async(
    device: Any,
    text: str,
    ui: UIMapper,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    post_type_delay: float = DEFAULT_POST_TYPE_DELAY,
    safe_send_only: bool = False,
) -> bool:
    """Async wrapper — runs send_chat_message in a thread."""
    return await asyncio.to_thread(
        send_chat_message,
        device,
        text,
        ui,
        max_attempts=max_attempts,
        post_type_delay=post_type_delay,
        safe_send_only=safe_send_only,
    )
