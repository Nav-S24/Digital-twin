"""
logger.py
=========
Central logger factory + a `timed` decorator, used across ingest,
retriever, rag_pipeline, api, and the app/services modules. Kept
dependency-light on purpose (no LangChain imports here) so this module
never becomes a source of circular imports.
"""

from __future__ import annotations

import functools
import logging
import sys
import time
from pathlib import Path
from typing import Callable, TypeVar

from app.config import settings

T = TypeVar("T")

_LOGGERS: dict[str, logging.Logger] = {}

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "app.log"


def get_logger(name: str) -> logging.Logger:
    """
    Central logger factory. Every module calls this instead of configuring
    its own handler, so log level and format are consistent and controlled
    in exactly one place (config.settings.log_level).

    Logs to stdout always, and additionally to logs/app.log when the logs/
    directory is writable (best-effort — never crashes a module import just
    because the log file can't be created, e.g. in a read-only container).
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    logger = logging.getLogger(name)
    logger.setLevel(settings.log_level)
    if not logger.handlers:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", "%H:%M:%S"
        )

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError:  # pragma: no cover - best-effort only
            pass

    logger.propagate = False
    _LOGGERS[name] = logger
    return logger


def timed(label: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that logs how long a function took. Used to satisfy the
    "performance timing" logging requirement without scattering
    time.perf_counter() calls through business logic.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            logger = get_logger(func.__module__)
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info("%s completed in %.1f ms", label, elapsed_ms)
            return result
        return wrapper
    return decorator
