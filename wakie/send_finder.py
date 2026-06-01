"""
Detect Wakie chat send button from live UI hierarchy.

Wakie often reveals the send control only after text is entered in the
input field — this module scans for it dynamically.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from utils.logger import get_logger

if TYPE_CHECKING:
    from wakie.ui_mapper import UIMapper

logger = get_logger(__name__)

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass
class SendTarget:
    """A clickable element that may submit the chat message."""

    method: str  # resource_id | content_desc | hierarchy | coordinate | ime | keyevent
    detail: str
    bounds: tuple[int, int, int, int] | None = None
    score: int = 0
    element: Any = None  # uiautomator2 element when resolved live


def _parse_bounds(raw: str) -> tuple[int, int, int, int] | None:
    match = _BOUNDS_RE.match(raw or "")
    if not match:
        return None
    return tuple(int(g) for g in match.groups())  # type: ignore[return-value]


def _center(bounds: tuple[int, int, int, int]) -> tuple[int, int]:
    left, top, right, bottom = bounds
    return (left + right) // 2, (top + bottom) // 2


class SendButtonFinder:
    """Locate Wakie send controls via resource-id, content-desc, or hierarchy scan."""

    SEND_DESC_KEYWORDS = ("send", "submit", "post message", "post")
    IMAGE_CLASSES = ("ImageButton", "ImageView", "AppCompatImageButton")

    def __init__(self, ui: UIMapper) -> None:
        self._ui = ui

    BLOCKED_RESOURCE_FRAGMENTS = (
        "action_filter",
        "air_action",
        "airAction",
        "navigate",
        "leave",
        "fab_mic",
        "swipe",
        "avatar",
        "header",
        "tab_",
    )

    def find(self, device: Any, *, safe_only: bool = False) -> list[SendTarget]:
        """
        Return send targets sorted by priority (best first).

        Combines known resource IDs, xpath content-desc probes, and a full
        hierarchy scan of the input container region.
        """
        targets: list[SendTarget] = []

        targets.extend(self._probe_resource_ids(device))
        if not safe_only:
            targets.extend(self._probe_content_desc(device))
            targets.extend(self._scan_hierarchy(device))

        # Deduplicate by bounds + method
        seen: set[str] = set()
        unique: list[SendTarget] = []
        for t in sorted(targets, key=lambda x: x.score, reverse=True):
            key = f"{t.method}:{t.detail}:{t.bounds}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(t)

        if unique:
            logger.debug(
                "Send candidates: %s",
                ", ".join(f"{t.method}={t.detail}(score={t.score})" for t in unique[:5]),
            )
        else:
            logger.debug("No send button candidates found in hierarchy")

        return unique

    def _probe_resource_ids(self, device: Any) -> list[SendTarget]:
        found: list[SendTarget] = []
        for rid in self._ui.send_button_candidates:
            try:
                el = device(resourceId=rid)
                if el.exists(timeout=0.3):
                    info = el.info
                    bounds = _parse_bounds(str(info.get("bounds", "")))
                    found.append(
                        SendTarget(
                            method="resource_id",
                            detail=rid,
                            bounds=bounds,
                            score=100,
                            element=el,
                        )
                    )
                    logger.debug("Send resource-id hit: %s", rid)
            except Exception as exc:
                logger.debug("Resource-id probe %s: %s", rid, exc)
        return found

    def _probe_content_desc(self, device: Any) -> list[SendTarget]:
        found: list[SendTarget] = []
        for keyword in self.SEND_DESC_KEYWORDS:
            xpath = (
                f'//*[@package="{self._ui.package}" and @clickable="true" '
                f'and contains(translate(@content-desc, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
                f'"abcdefghijklmnopqrstuvwxyz"), "{keyword}")]'
            )
            try:
                for el in device.xpath(xpath).all():
                    info = el.info
                    desc = info.get("contentDescription") or info.get("content-desc") or keyword
                    bounds = _parse_bounds(str(info.get("bounds", "")))
                    if self._is_in_input_region(bounds):
                        found.append(
                            SendTarget(
                                method="content_desc",
                                detail=str(desc),
                                bounds=bounds,
                                score=90,
                                element=el,
                            )
                        )
            except Exception as exc:
                logger.debug("Content-desc xpath %s: %s", keyword, exc)
        return found

    def _scan_hierarchy(self, device: Any) -> list[SendTarget]:
        """Parse XML hierarchy for clickable send-like nodes near the input bar."""
        try:
            xml = device.dump_hierarchy(compressed=True)
        except Exception as exc:
            logger.warning("Hierarchy dump failed: %s", exc)
            return []

        input_bounds = self._get_input_container_bounds(device)
        found: list[SendTarget] = []

        try:
            root = ET.fromstring(xml)
        except ET.ParseError as exc:
            logger.warning("Hierarchy parse error: %s", exc)
            return []

        for node in root.iter("node"):
            if node.get("clickable") != "true":
                continue
            if node.get("package") != self._ui.package:
                continue

            rid = node.get("resource-id") or ""
            desc = (node.get("content-desc") or "").lower()
            cls = node.get("class") or ""
            bounds_raw = node.get("bounds") or ""
            bounds = _parse_bounds(bounds_raw)

            if rid == self._ui.chat_input_id:
                continue
            if any(block in rid for block in self.BLOCKED_RESOURCE_FRAGMENTS):
                continue

            score = 0
            rid_lower = rid.lower()

            if "send" in rid_lower:
                score += 80
            if any(kw in desc for kw in self.SEND_DESC_KEYWORDS):
                score += 70
            if any(img in cls for img in self.IMAGE_CLASSES):
                score += 30

            if score == 0:
                continue

            if input_bounds and bounds:
                if not self._near_input_region(bounds, input_bounds):
                    score -= 40
                    if score <= 0:
                        continue

            found.append(
                SendTarget(
                    method="hierarchy",
                    detail=rid or desc or cls,
                    bounds=bounds,
                    score=score,
                    element=self._resolve_element(device, rid) if rid else None,
                )
            )

        return found

    def _resolve_element(self, device: Any, resource_id: str) -> Any | None:
        try:
            el = device(resourceId=resource_id)
            if el.exists(timeout=0.2):
                return el
        except Exception:
            pass
        return None

    def _get_input_container_bounds(self, device: Any) -> tuple[int, int, int, int] | None:
        try:
            container = device(resourceId=self._ui.input_container_id)
            if container.exists(timeout=0.5):
                return _parse_bounds(str(container.info.get("bounds", "")))
            inp = device(resourceId=self._ui.chat_input_id)
            if inp.exists(timeout=0.5):
                return _parse_bounds(str(inp.info.get("bounds", "")))
        except Exception:
            pass
        return None

    def _is_in_input_region(self, bounds: tuple[int, int, int, int] | None) -> bool:
        if bounds is None:
            return True
        _left, top, _right, bottom = bounds
        # Input bar is typically in the bottom ~15% of screen
        return top >= 1400 and bottom <= 1600

    def _near_input_region(
        self,
        bounds: tuple[int, int, int, int],
        input_bounds: tuple[int, int, int, int],
    ) -> bool:
        left, top, right, bottom = bounds
        il, it, ir, ib = input_bounds
        cy = (top + bottom) // 2
        return (it - 20) <= cy <= (ib + 20) and right >= (il + (ir - il) // 2)

    def coordinate_fallback(self, device: Any) -> SendTarget | None:
        """Tap point on the right edge of the input bar (send icon area)."""
        bounds = self._get_input_container_bounds(device)
        if bounds is None:
            return None
        left, top, right, bottom = bounds
        # Right-side inset where send icons usually appear
        tap_x = max(right - 40, left + (right - left) * 3 // 4)
        tap_y = (top + bottom) // 2
        return SendTarget(
            method="coordinate",
            detail=f"({tap_x},{tap_y})",
            bounds=(tap_x - 1, tap_y - 1, tap_x + 1, tap_y + 1),
            score=20,
        )
