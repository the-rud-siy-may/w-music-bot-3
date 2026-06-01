"""
Wakie chat message reader.

Connects to LDPlayer via uiautomator2, extracts visible chat messages from
the Android UI hierarchy, and falls back to EasyOCR on a cropped screenshot
when direct text extraction fails.

Duplicate reads are prevented via stable content fingerprints and a rolling
seen-message cache.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, TYPE_CHECKING

from utils.logger import get_logger

if TYPE_CHECKING:
    import uiautomator2 as u2

    from config import BotConfig
    from wakie.device_session import DeviceSession
    from wakie.ui_mapper import UIMapper, UIRegion

logger = get_logger(__name__)

# Patterns for parsing combined "username: message" OCR / UI lines
_USERNAME_MESSAGE_RE = re.compile(r"^(.{1,40}?)\s*[:：]\s*(.+)$")
_TIMESTAMP_RE = re.compile(
    r"^(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?|\d{1,2}h\s*\d{0,2}m?)$"
)


@dataclass
class ChatMessage:
    """A single message observed in the Wakie chat panel."""

    username: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_id: str = ""
    source: str = "ui"  # "ui" | "ocr"
    bubble_bounds: tuple[int, int, int, int] | None = None

    def __post_init__(self) -> None:
        if not self.message_id:
            self.message_id = _content_fingerprint(
                self.username,
                self.message,
                self.timestamp.isoformat(),
            )

    @property
    def text(self) -> str:
        """Alias used by command parser / detector."""
        return self.message

    def to_dict(self) -> dict[str, str]:
        """Return the structured message format expected by downstream code."""
        return {
            "username": self.username,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class _TextNode:
    """Internal representation of a text-bearing UI or OCR node."""

    text: str
    top: int
    left: int
    bottom: int
    right: int
    resource_id: str = ""
    content_desc: str = ""

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2


def _content_fingerprint(username: str, message: str, anchor: str = "") -> str:
    """Stable hash for deduplicating message reads across polls."""
    payload = f"{username.strip().lower()}|{message.strip()}|{anchor}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _parse_bounds(raw: Any) -> tuple[int, int, int, int] | None:
    """Parse uiautomator2 bounds dict or string into (left, top, right, bottom)."""
    if raw is None:
        return None

    if isinstance(raw, dict):
        return (
            int(raw.get("left", 0)),
            int(raw.get("top", 0)),
            int(raw.get("right", 0)),
            int(raw.get("bottom", 0)),
        )

    if isinstance(raw, str):
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", raw)
        if match:
            return tuple(int(g) for g in match.groups())  # type: ignore[return-value]

    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        return int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3])

    return None


class UIChatExtractor:
    """Extract chat messages directly from the Android UI hierarchy."""

    def __init__(self, ui: UIMapper, package: str) -> None:
        self._ui = ui
        self._package = package

    def extract(self, device: u2.Device) -> list[ChatMessage]:
        """
        Walk the UI tree and return structured messages.

        Strategy (no hardcoded coordinates):
          1. Locate chat container by resource-id / class selectors
          2. Try structured row extraction (username + message child nodes)
          3. Fall back to grouping all TextViews by vertical position
        """
        container = self._find_chat_container(device)
        if container is None:
            logger.warning("Chat container not found via UI selectors")
            return []

        bounds = _parse_bounds(container.info.get("bounds"))
        if bounds is None:
            logger.warning("Chat container has no bounds")
            return []

        # Attempt structured row parsing first
        messages = self._extract_structured_rows(device, container)
        if messages:
            logger.debug("UI structured extraction: %d message(s)", len(messages))
            return messages

        # Flat TextView grouping inside container bounds
        nodes = self._collect_text_nodes(device, bounds)
        messages = _group_nodes_into_messages(nodes, source="ui")
        logger.debug("UI flat extraction: %d message(s) from %d node(s)", len(messages), len(nodes))
        return messages

    def get_container_region(self, device: u2.Device) -> UIRegion | None:
        """Return the live bounds of the chat container for OCR cropping."""
        from wakie.ui_mapper import UIRegion

        container = self._find_chat_container(device)
        if container is None:
            return None
        bounds = _parse_bounds(container.info.get("bounds"))
        if bounds is None:
            return None
        left, top, right, bottom = bounds
        return UIRegion.from_bounds(left, top, right, bottom)

    def _find_chat_container(self, device: u2.Device) -> Any | None:
        """Try each configured selector until a visible container is found."""
        for spec in self._ui.chat_container_selectors:
            try:
                elem = device(**spec)
                if elem.exists(timeout=0.5):
                    logger.debug("Chat container matched: %s", spec)
                    return elem
            except Exception as exc:
                logger.debug("Selector %s failed: %s", spec, exc)

        xpath = self._ui.get_selector("chat_list")
        if xpath:
            try:
                elem = device.xpath(xpath)
                if elem.exists:
                    logger.debug("Chat container matched xpath: %s", xpath)
                    return elem
            except Exception as exc:
                logger.debug("XPath %s failed: %s", xpath, exc)

        return None

    def _extract_structured_rows(self, device: u2.Device, container: Any) -> list[ChatMessage]:
        """Parse message rows that expose username / message / timestamp resource IDs."""
        messages: list[ChatMessage] = []

        for row_xpath in self._ui.chat_row_xpaths():
            if not row_xpath:
                continue
            try:
                rows = device.xpath(row_xpath).all()
            except Exception:
                continue

            for row in rows:
                msg = self._parse_row_element(row)
                if msg is not None:
                    messages.append(msg)

            if messages:
                break

        return messages

    def _parse_row_element(self, row: Any) -> ChatMessage | None:
        """Extract username, message, and optional timestamp from a row node."""
        try:
            info = row.info
        except Exception:
            return None

        username = ""
        message = ""
        timestamp = datetime.now(timezone.utc)

        # Try dedicated child resource IDs
        for attr, target in (("username", "username"), ("message", "message")):
            rid = getattr(self._ui, f"{target}_id", "")
            if rid:
                try:
                    child = row.child(resourceId=rid)
                    if child.exists(timeout=0):
                        text = (child.info.get("text") or "").strip()
                        if attr == "username":
                            username = text
                        else:
                            message = text
                except Exception:
                    pass

        # Timestamp child
        ts_id = self._ui.timestamp_id
        if ts_id:
            try:
                ts_child = row.child(resourceId=ts_id)
                if ts_child.exists(timeout=0):
                    ts_text = (ts_child.info.get("text") or "").strip()
                    parsed = _parse_timestamp_text(ts_text)
                    if parsed:
                        timestamp = parsed
            except Exception:
                pass

        # Fallback: all text children in row
        if not message:
            texts = self._texts_from_subtree(row)
            if not texts:
                return None
            if len(texts) >= 2 and not _TIMESTAMP_RE.match(texts[0]):
                username = username or texts[0]
                message = " ".join(t for t in texts[1:] if not _TIMESTAMP_RE.match(t))
            elif len(texts) == 1:
                parsed = _parse_combined_line(texts[0])
                if parsed:
                    username, message = parsed
                else:
                    message = texts[0]

        message = message.strip()
        if not message or _is_noise_text(message):
            return None

        if not username:
            username = "unknown"

        anchor = str(info.get("resourceId", "")) + str(info.get("bounds", ""))
        bubble_bounds = _parse_bounds(info.get("bounds"))
        return ChatMessage(
            username=username,
            message=message,
            timestamp=timestamp,
            message_id=_content_fingerprint(username, message, anchor),
            source="ui",
            bubble_bounds=bubble_bounds,
        )

    def _texts_from_subtree(self, node: Any) -> list[str]:
        """Collect non-empty text values from a node and its descendants."""
        texts: list[str] = []
        try:
            info = node.info
            if info.get("text"):
                texts.append(info["text"].strip())
        except Exception:
            pass

        try:
            for child in node.child():
                child_text = (child.info.get("text") or "").strip()
                if child_text:
                    texts.append(child_text)
        except Exception:
            pass

        return texts

    def _collect_text_nodes(
        self,
        device: u2.Device,
        clip_bounds: tuple[int, int, int, int],
    ) -> list[_TextNode]:
        """Gather all visible TextView nodes within the chat container bounds."""
        left, top, right, bottom = clip_bounds
        nodes: list[_TextNode] = []

        try:
            elements = device.xpath('//*[@text!=""]').all()
        except Exception as exc:
            logger.debug("TextView xpath scan failed: %s", exc)
            return nodes

        for elem in elements:
            try:
                info = elem.info
                text = (info.get("text") or "").strip()
                if not text or _is_noise_text(text):
                    continue

                bounds = _parse_bounds(info.get("bounds"))
                if bounds is None:
                    continue

                b_left, b_top, b_right, b_bottom = bounds
                # Keep nodes inside the chat container
                if b_top < top or b_bottom > bottom + 2:
                    continue
                if b_left < left - 10 or b_right > right + 10:
                    continue

                nodes.append(
                    _TextNode(
                        text=text,
                        top=b_top,
                        left=b_left,
                        bottom=b_bottom,
                        right=b_right,
                        resource_id=info.get("resourceId") or "",
                        content_desc=info.get("contentDescription") or "",
                    )
                )
            except Exception:
                continue

        nodes.sort(key=lambda n: (n.top, n.left))
        return nodes


class OCRChatExtractor:
    """Screenshot + EasyOCR fallback when UI text extraction fails."""

    def __init__(self, languages: list[str], cache_dir: Any) -> None:
        self._languages = languages
        self._cache_dir = cache_dir
        self._reader: Any = None

    def _get_reader(self) -> Any:
        """Lazy-init EasyOCR (heavy import)."""
        if self._reader is None:
            import easyocr

            logger.info("Initialising EasyOCR reader (languages=%s)", self._languages)
            self._reader = easyocr.Reader(self._languages, gpu=False, verbose=False)
        return self._reader

    def extract_from_region(
        self,
        device: u2.Device,
        region: UIRegion,
    ) -> list[ChatMessage]:
        """
        Capture a screenshot, crop to the chat container bounds, and OCR.

        Bounds come from the live UI element — never hardcoded.
        """
        import numpy as np

        screenshot = device.screenshot()
        left, top, right, bottom = region.bounds

        # Clamp to screenshot dimensions
        width, height = screenshot.size
        left = max(0, min(left, width))
        top = max(0, min(top, height))
        right = max(left, min(right, width))
        bottom = max(top, min(bottom, height))

        if right - left < 10 or bottom - top < 10:
            logger.warning("OCR region too small: %s", region.bounds)
            return []

        cropped = screenshot.crop((left, top, right, bottom))
        img_array = np.array(cropped)

        # Optional debug artefact
        try:
            debug_path = self._cache_dir / "last_ocr_crop.png"
            cropped.save(debug_path)
            logger.debug("OCR crop saved → %s", debug_path)
        except Exception:
            pass

        reader = self._get_reader()
        results = reader.readtext(img_array, paragraph=False)

        nodes: list[_TextNode] = []
        for bbox, text, confidence in results:
            if confidence < 0.3 or not text.strip():
                continue
            ys = [p[1] for p in bbox]
            xs = [p[0] for p in bbox]
            nodes.append(
                _TextNode(
                    text=text.strip(),
                    top=int(min(ys)) + top,
                    left=int(min(xs)) + left,
                    bottom=int(max(ys)) + top,
                    right=int(max(xs)) + left,
                )
            )

        nodes.sort(key=lambda n: (n.top, n.left))
        messages = _group_nodes_into_messages(nodes, source="ocr")
        logger.info("OCR extraction: %d message(s) from %d line(s)", len(messages), len(nodes))
        return messages


def _group_nodes_into_messages(
    nodes: list[_TextNode],
    source: str,
    row_threshold: int = 40,
) -> list[ChatMessage]:
    """
    Cluster text nodes into rows by Y proximity, then parse each row.

    Handles layouts where username and message appear on separate lines or
    combined as 'username: message'.
    """
    if not nodes:
        return []

    rows: list[list[_TextNode]] = []
    current_row: list[_TextNode] = [nodes[0]]

    for node in nodes[1:]:
        if abs(node.center_y - current_row[-1].center_y) <= row_threshold:
            current_row.append(node)
        else:
            rows.append(current_row)
            current_row = [node]
    rows.append(current_row)

    messages: list[ChatMessage] = []
    pending_username: str | None = None

    for row in rows:
        texts = [n.text for n in sorted(row, key=lambda n: n.left) if n.text.strip()]
        if not texts:
            continue

        # Filter standalone timestamps
        filtered = [t for t in texts if not _TIMESTAMP_RE.match(t)]
        if not filtered:
            continue

        username = ""
        message = ""
        ts = datetime.now(timezone.utc)

        if len(filtered) >= 2:
            username = filtered[0]
            message = " ".join(filtered[1:])
        elif len(filtered) == 1:
            combined = _parse_combined_line(filtered[0])
            if combined:
                username, message = combined
            elif pending_username:
                username = pending_username
                message = filtered[0]
                pending_username = None
            elif len(filtered[0]) <= 30 and not filtered[0].startswith("/"):
                # Short line might be a username for the next row
                pending_username = filtered[0]
                continue
            else:
                message = filtered[0]

        message = message.strip()
        if not message or _is_noise_text(message):
            continue

        if not username:
            username = pending_username or "unknown"
            pending_username = None

        anchor = "|".join(n.text for n in row)
        messages.append(
            ChatMessage(
                username=username,
                message=message,
                timestamp=ts,
                message_id=_content_fingerprint(username, message, anchor),
                source=source,
            )
        )

    return messages


def _parse_combined_line(line: str) -> tuple[str, str] | None:
    """Parse 'username: message' into a tuple."""
    match = _USERNAME_MESSAGE_RE.match(line.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None


def _parse_timestamp_text(text: str) -> datetime | None:
    """Best-effort parse of a visible timestamp string."""
    text = text.strip()
    if not _TIMESTAMP_RE.match(text):
        return None
    # Use today's date as anchor — good enough for dedup, not archival
    now = datetime.now(timezone.utc)
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
        try:
            parsed = datetime.strptime(text, fmt)
            return now.replace(hour=parsed.hour, minute=parsed.minute, second=parsed.second, microsecond=0)
        except ValueError:
            continue
    return None


def _is_noise_text(text: str) -> bool:
    """Filter out UI chrome that is not chat content."""
    lower = text.lower()
    noise = (
        "type a message",
        "send message",
        "wakie",
        "connected",
        "connecting",
        "loading",
    )
    return any(n in lower for n in noise) or len(text) < 1


class MessageReader:
    """
    Reads visible chat messages from the LDPlayer Wakie window.

    Flow:
      connect() → uiautomator2 session
      read_messages() → UI extract → OCR fallback → deduplicate
    """

    def __init__(
        self,
        config: BotConfig,
        ui_mapper: UIMapper,
        session: DeviceSession | None = None,
    ) -> None:
        from wakie.wakie_extractor import WakieChatExtractor

        self._config = config
        self._ui = ui_mapper
        self._session = session
        self._device: u2.Device | None = None
        self._connected = False

        self._wakie_extractor = WakieChatExtractor(ui_mapper)
        self._ui_extractor = UIChatExtractor(ui_mapper, config.wakie_package)
        self._ocr_extractor = OCRChatExtractor(
            languages=config.reader_ocr_languages,
            cache_dir=config.cache_dir,
        )

        # Duplicate-read prevention
        self._seen_ids: deque[str] = deque(maxlen=config.reader_max_seen_cache)
        self._seen_set: set[str] = set()
        self._last_visible: list[ChatMessage] = []

        logger.debug(
            "MessageReader initialized (serial=%s, poll=%.1fs, ocr=%s)",
            config.adb_serial,
            config.poll_interval,
            config.reader_ocr_enabled,
        )

    @property
    def poll_interval(self) -> float:
        """Configurable polling interval (seconds)."""
        return self._config.poll_interval

    @property
    def is_connected(self) -> bool:
        return self._connected and self._device is not None

    @property
    def device(self) -> u2.Device | None:
        return self._device

    # ── Connection lifecycle ───────────────────────────────────────────────

    async def connect(self) -> None:
        """Connect to LDPlayer via uiautomator2 with retries."""
        if self._session is not None:
            await self._session.connect()
            self._device = self._session.device
            self._connected = True
            logger.info("MessageReader using shared device session")
            return

        logger.info("Connecting to LDPlayer at %s", self._config.adb_serial)

        def _connect_sync() -> u2.Device:
            import uiautomator2 as u2

            device = u2.connect(self._config.adb_serial)
            device.implicitly_wait(1.0)

            # Ensure Wakie is in foreground (best-effort)
            try:
                device.app_wait(self._config.wakie_package, timeout=self._config.reader_connect_timeout)
            except Exception as exc:
                logger.warning("Wakie app wait timed out: %s", exc)

            info = device.info
            logger.info(
                "Connected: %s (%s) — display %sx%s",
                info.get("productName", "unknown"),
                info.get("serial", self._config.adb_serial),
                info.get("displayWidth", "?"),
                info.get("displayHeight", "?"),
            )
            return device

        self._device = await self._with_retry(_connect_sync, label="connect")
        self._connected = True

        # Optionally refine selectors from hierarchy
        await self._refine_ui_mapping()

    async def disconnect(self) -> None:
        """Release the uiautomator2 session."""
        if self._session is None:
            self._device = None
        self._connected = False
        logger.info("MessageReader disconnected")

    async def _refine_ui_mapping(self) -> None:
        """Attempt to auto-detect chat container resource IDs from hierarchy."""
        if self._device is None:
            return

        def _dump() -> str:
            return self._device.dump_hierarchy(compressed=True)  # type: ignore[union-attr]

        try:
            xml = await asyncio.to_thread(_dump)
            if "chat" in xml.lower() or "message" in xml.lower():
                logger.debug("Hierarchy dump contains chat/message nodes")
        except Exception as exc:
            logger.debug("Hierarchy dump skipped: %s", exc)

    # ── Message reading ────────────────────────────────────────────────────

    async def read_messages(self) -> list[ChatMessage]:
        """
        Read all currently visible chat messages.

        Tries direct UI extraction first, then OCR screenshot fallback.
        Returns deduplicated structured ChatMessage objects.
        """
        if not self.is_connected or self._device is None:
            logger.error("read_messages called before connect()")
            return list(self._last_visible)

        messages: list[ChatMessage] = []

        # Primary: Wakie bubble extraction (confirmed resource IDs)
        try:
            messages = await self._with_retry(
                lambda: self._wakie_extractor.extract(self._device),
                label="wakie_extract",
            )
        except Exception as exc:
            logger.warning("Wakie extraction failed: %s", exc)

        # Secondary: generic Android UI extraction
        if not messages:
            try:
                messages = await self._with_retry(
                    lambda: self._ui_extractor.extract(self._device),
                    label="ui_extract",
                )
            except Exception as exc:
                logger.warning("UI extraction failed after retries: %s", exc)

        # Fallback: screenshot OCR
        if not messages and self._config.reader_ocr_enabled:
            try:
                region = await asyncio.to_thread(
                    self._ui_extractor.get_container_region,
                    self._device,
                )
                if region is not None:
                    messages = await self._with_retry(
                        lambda: self._ocr_extractor.extract_from_region(self._device, region),
                        label="ocr_extract",
                    )
                else:
                    logger.warning("OCR skipped — chat container bounds unavailable")
            except Exception as exc:
                logger.error("OCR extraction failed: %s", exc, exc_info=True)

        messages = self._deduplicate(messages)
        self._last_visible = messages

        if messages:
            logger.debug(
                "Read %d visible message(s) [%s]",
                len(messages),
                ", ".join(m.source for m in messages),
            )
        else:
            logger.debug("No messages extracted this poll")

        return list(messages)

    async def read_new_messages(self) -> list[ChatMessage]:
        """
        Read messages and return only those not seen in prior polls.

        Convenience wrapper combining read_messages() with internal dedup.
        """
        visible = await self.read_messages()
        new: list[ChatMessage] = []
        for msg in visible:
            if msg.message_id in self._seen_set:
                continue
            self._register_seen(msg.message_id)
            new.append(msg)
        return new

    # ── Duplicate prevention ─────────────────────────────────────────────────

    def _deduplicate(self, messages: list[ChatMessage]) -> list[ChatMessage]:
        """Remove duplicate messages within a single read pass."""
        seen: set[str] = set()
        unique: list[ChatMessage] = []
        for msg in messages:
            if msg.message_id in seen:
                continue
            seen.add(msg.message_id)
            unique.append(msg)
        return unique

    def _register_seen(self, message_id: str) -> None:
        """Track a message ID in the rolling seen cache."""
        if message_id in self._seen_set:
            return
        if len(self._seen_ids) >= self._config.reader_max_seen_cache:
            evicted = self._seen_ids.popleft()
            self._seen_set.discard(evicted)
        self._seen_ids.append(message_id)
        self._seen_set.add(message_id)

    def clear_seen_cache(self) -> None:
        """Reset duplicate-tracking state (e.g. after entering a new chat)."""
        self._seen_ids.clear()
        self._seen_set.clear()
        logger.info("Reader seen-cache cleared")

    # ── Retry helper ───────────────────────────────────────────────────────

    async def _with_retry(
        self,
        fn: Callable[[], Any],
        label: str = "operation",
    ) -> Any:
        """Run a blocking callable in a thread with exponential backoff retries."""
        attempts = self._config.reader_retry_attempts
        delay = self._config.reader_retry_delay
        last_exc: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.to_thread(fn)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "%s attempt %d/%d failed: %s",
                    label,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt < attempts:
                    await asyncio.sleep(delay * attempt)

        raise RuntimeError(f"{label} failed after {attempts} attempts") from last_exc

    # ── Test / dev helpers ─────────────────────────────────────────────────

    def inject_message(self, username: str, text: str) -> ChatMessage:
        """Inject a synthetic message for testing without a device."""
        msg = ChatMessage(username=username, message=text, source="inject")
        self._last_visible.append(msg)
        self._register_seen(msg.message_id)
        return msg
