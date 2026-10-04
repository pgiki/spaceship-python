"""Logging setup for spaceship-python."""

from __future__ import annotations

import logging

_logger = logging.getLogger("spaceship")


def set_log_level(level: str) -> None:
    """Set the log level for the ``spaceship`` logger."""
    _logger.setLevel(getattr(logging, str(level or "INFO").upper(), logging.INFO))


def get_logger(name: str) -> logging.Logger:
    """Child logger under the ``spaceship`` namespace."""
    return logging.getLogger(f"spaceship.{name}")
