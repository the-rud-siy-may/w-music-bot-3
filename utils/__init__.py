"""
Shared utilities for the Wakie music assistant bot.

Import submodules directly (e.g. utils.permissions) to avoid eager import
chains through this package init.
"""

from utils.logger import get_logger, setup_logging
from utils.constants import CommandTier, COMMAND_REGISTRY, TIER_ORDER

__all__ = [
    "get_logger",
    "setup_logging",
    "CommandTier",
    "COMMAND_REGISTRY",
    "TIER_ORDER",
]
