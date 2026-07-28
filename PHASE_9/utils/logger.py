"""
utils/logger.py

Centralized logging setup. Every module calls `get_logger(__name__)`
so log records are consistently formatted and, on request, written to
both console and a rotating log file under `logs/`.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from config.settings import PATHS

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_CONFIGURED_LOGGERS = set()


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Return a configured logger instance.

    Args:
        name: Usually `__name__` of the calling module.
        level: Logging level, defaults to INFO.

    Returns:
        A `logging.Logger` with a console handler and a rotating file
        handler already attached (attached only once per logger name).
    """
    logger = logging.getLogger(name)

    if name in _CONFIGURED_LOGGERS:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    try:
        os.makedirs(PATHS.log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(PATHS.log_dir, "phase9_driver_behavior.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except OSError:
        # If the filesystem is read-only or log_dir cannot be created,
        # fall back to console-only logging instead of crashing.
        logger.warning("Could not attach file handler; logging to console only.")

    _CONFIGURED_LOGGERS.add(name)
    return logger
