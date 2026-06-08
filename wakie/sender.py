"""
Send chat messages via uiautomator2.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from utils.logger import get_logger
from wakie.chat import send_chat_message_async
from wakie.chat_actions import send_reply_to_message

if TYPE_CHECKING:
    from config import BotConfig
    from wakie.device_session import DeviceSession
    from wakie.message_filter import MessageFilter
    from wakie.reader import ChatMessage
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

    async def send(self, text: str, *, reply_to: ChatMessage | None = None) -> bool:
        if self._config.muted:
            logger.info("Muted — not sending: %s", text[:60])
            return False
        if self._session is None or not self._session.is_connected:
            logger.error("Cannot send — not connected")
            return False

        device = self._session.device
        if reply_to is not None:
            ok = await asyncio.to_thread(
                send_reply_to_message,
                device,
                self._ui,
                text,
                reply_to,
                post_type_delay=self._config.send_post_type_delay,
                safe_send_only=self._config.safe_send_only,
            )
            if not ok:
                logger.warning("Reply failed — falling back to plain send")
                ok = await send_chat_message_async(
                    device,
                    text,
                    self._ui,
                    max_attempts=self._config.send_retry_attempts,
                    post_type_delay=self._config.send_post_type_delay,
                    safe_send_only=self._config.safe_send_only,
                )
        else:
            ok = await send_chat_message_async(
                device,
                text,
                self._ui,
                max_attempts=self._config.send_retry_attempts,
                post_type_delay=self._config.send_post_type_delay,
                safe_send_only=self._config.safe_send_only,
            )
        if ok and self._filter is not None:
            self._filter.register_outbound(text)
        return ok

    def note_incoming_command(self, msg: ChatMessage) -> None:
        """Mark this command bubble so reply previews are not re-processed."""
        if self._filter is not None:
            self._filter.register_command_handled(msg.message, message_id=msg.message_id)

    async def disconnect(self) -> None:
        pass
