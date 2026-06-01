"""
Wakie Music Assistant Bot — MVP entry point.

Run: python main.py

Requires:
  - LDPlayer with Wakie open on the voice-chat screen
  - ADB connected (default serial: emulator-5554)
  - Local songs in songs/  (e.g. songs/faded.mp3)
  - VLC installed (python-vlc)
"""

from __future__ import annotations

import asyncio
import sys

from bot.runtime import WakieBot
from config import load_config
from utils.logger import setup_logging, get_logger

logger = get_logger(__name__)


async def _async_main() -> None:
    config = load_config()
    setup_logging(log_dir=config.log_dir)

    bot = WakieBot(config)

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Shutting down…")
    finally:
        await bot.stop()


def main() -> None:
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
