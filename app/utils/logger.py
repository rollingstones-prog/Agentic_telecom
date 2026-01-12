# app/utils/logger.py

from __future__ import annotations
import logging
import sys

from app.core.config import LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    """
    Central logger factory.
    Ensures consistent formatting across the Agentic OS.
    """

    logger = logging.getLogger(name)

    if logger.handlers:
        return logger  # Prevent duplicate handlers

    logger.setLevel(LOG_LEVEL)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger
