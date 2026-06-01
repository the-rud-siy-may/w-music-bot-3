"""
Logging setup for the Wakie music assistant bot.

Provides a consistent formatter and optional file handler under logs/.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_configured = False


def setup_logging(
    log_dir: Path | None = None,
    level: int = logging.INFO,
    log_to_file: bool = True,
) -> None:
    """
    Configure root logging once for the entire application.

    Args:
        log_dir: Directory for daily log files. Created if missing.
        level: Root log level.
        log_to_file: When True, also write to a dated log file.
    """
    global _configured
    if _configured:
        return

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
    ]

    if log_to_file and log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"wakie_bot_{datetime.now():%Y%m%d}.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        handlers=handlers,
        force=True,
    )
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger; call setup_logging() first from main."""
    return logging.getLogger(name)
