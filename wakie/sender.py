"""
Send chat messages via uiautomator2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from utils.logger import get_logger
from wakie.chat import send_chat_message_async

if TYPE_CHECKING:
    from config import BotConfig
    from wakie.device_session import DeviceSession
    from wakie.message_filter import MessageFilter
    from wakie.ui_mapper import UIMapper

logger = get_logger(__name__)


class MessageSender:
    def __init__(
        self,
        config: BotConfig,
        ui_mapper: UIMapper,
        session: DeviceSession | None = None,
        message_filter: MessageFilter | None = None,
    ) -> None:
        self._config = config
        self._ui = ui_mapper
        self._session = session
        self._filter = message_filter

    async def connect(self) -> None:
        if self._session and not self._session.is_connected:
            await self._session.connect()

    async def send(self, text: str) -> bool:
        if self._config.muted:
            logger.info("Muted — not sending: %s", text[:60])
            return False
        if self._session is None or not self._session.is_connected:
            logger.error("Cannot send — not connected")
            return False

        ok = await send_chat_message_async(
            self._session.device,
            text,
            self._ui,
            max_attempts=self._config.send_retry_attempts,
            post_type_delay=self._config.send_post_type_delay,
            safe_send_only=self._config.safe_send_only,
        )
        if ok and self._filter is not None:
            self._filter.register_outbound(text)
        return ok

    async def disconnect(self) -> None:
        pass
