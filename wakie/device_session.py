"""
Shared uiautomator2 device session for reader and sender.

One connection per bot instance — avoids duplicate ADB sessions.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from utils.logger import get_logger

if TYPE_CHECKING:
    import uiautomator2 as u2

    from config import BotConfig

logger = get_logger(__name__)


class DeviceSession:
    """Manages a single uiautomator2 connection to LDPlayer."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config
        self._device: u2.Device | None = None

    @property
    def is_connected(self) -> bool:
        return self._device is not None

    @property
    def device(self) -> Any:
        if self._device is None:
            raise RuntimeError("Device not connected — call connect() first")
        return self._device

    async def connect(self) -> None:
        """Connect to LDPlayer and bring Wakie to the foreground."""
        if self._device is not None:
            return

        def _connect_sync() -> u2.Device:
            import uiautomator2 as u2

            serial = self._config.adb_serial
            logger.info("Connecting uiautomator2 → %s", serial)
            device = u2.connect(serial)
            device.implicitly_wait(1.0)

            try:
                device.app_wait(self._config.wakie_package, timeout=self._config.reader_connect_timeout)
            except Exception as exc:
                logger.warning("Wakie foreground wait: %s", exc)

            info = device.info
            logger.info(
                "Device ready: %sx%s serial=%s",
                info.get("displayWidth", "?"),
                info.get("displayHeight", "?"),
                info.get("serial", serial),
            )
            return device

        self._device = await asyncio.to_thread(_connect_sync)

    async def disconnect(self) -> None:
        self._device = None
        logger.info("Device session closed")
