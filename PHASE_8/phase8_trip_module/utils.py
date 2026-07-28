"""
utils.py
Phase 8 - Trip Intelligence Module
Shared helper functions: logging setup, geo math, safe-casting, formatting.
"""

from __future__ import annotations

import logging
import math
import os
from functools import lru_cache
from typing import Any, Optional

from config import settings


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger that writes to console + rotating file."""
    os.makedirs(settings.log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    file_path = os.path.join(settings.log_dir, settings.log_file)
    file_handler = logging.FileHandler(file_path)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points in kilometers."""
    r = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def safe_float(value: Any, default: float = 0.0) -> float:
    """Cast to float, returning a default on failure."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def format_currency(amount: float) -> str:
    return f"{settings.currency_symbol}{amount:,.0f}"


def pct(value: float) -> str:
    """Format a 0-1 fraction as a percentage string."""
    return f"{value * 100:.1f}%"
