"""
utils/helpers.py
================
Stateless utility functions used across the twin, services, and API layers.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from config.settings import HEALTH_THRESHOLDS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    """Return current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def iso_to_datetime(iso: str) -> datetime:
    """Parse an ISO-8601 string (with or without timezone) to datetime."""
    try:
        return datetime.fromisoformat(iso)
    except ValueError:
        return datetime.strptime(iso, "%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Health scoring utilities
# ---------------------------------------------------------------------------

def classify_health(score: float) -> str:
    """
    Map a numeric health score [0, 100] to a categorical label.

    Thresholds (from config/settings.py):
        Excellent  85 – 100
        Good       65 –  84.9
        Warning    40 –  64.9
        Critical    0 –  39.9
    """
    for label, (lo, hi) in HEALTH_THRESHOLDS.items():
        if lo <= score <= hi:
            return label
    return "Critical"  # fallback for out-of-range values


def sensor_sub_score(
    value: float,
    optimal_low: float,
    optimal_high: float,
    max_val: float,
    critical: float,
    lower_is_worse: bool = False,
) -> float:
    """
    Normalise a raw sensor reading to a 0–100 sub-score.

    The scoring surface is piecewise linear:
        - In [optimal_low, optimal_high]  → 100 (perfect)
        - Between optimal and critical    → linear decay towards 0
        - Beyond critical                 → 0

    Parameters
    ----------
    value        : raw sensor reading
    optimal_low  : lower bound of the ideal operating range
    optimal_high : upper bound of the ideal operating range
    max_val      : physical maximum (used for normalisation)
    critical     : threshold beyond which score collapses to 0
    lower_is_worse : if True, values *below* optimal_low are penalised
    """
    if optimal_low <= value <= optimal_high:
        return 100.0

    if not lower_is_worse:
        # Penalise values ABOVE optimal_high
        if value > optimal_high:
            if value >= critical:
                return 0.0
            ratio = (value - optimal_high) / (critical - optimal_high)
            return max(0.0, 100.0 * (1.0 - ratio))
        # Values below optimal_low are fine in this direction
        return 100.0
    else:
        # Penalise values BELOW optimal_low
        if value < optimal_low:
            if value <= critical:
                return 0.0
            ratio = (optimal_low - value) / (optimal_low - critical)
            return max(0.0, 100.0 * (1.0 - ratio))
        return 100.0


def clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, float(value)))


def weighted_average(values: Dict[str, float], weights: Dict[str, float]) -> float:
    """
    Compute a weighted average from two parallel dicts sharing the same keys.

    Parameters
    ----------
    values  : {component_name: score}
    weights : {component_name: weight}

    Returns
    -------
    float in [0, 100]
    """
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(values[k] * weights.get(k, 0.0) for k in values)
    return clamp(weighted_sum / total_weight)


# ---------------------------------------------------------------------------
# Maintenance recommendation helpers
# ---------------------------------------------------------------------------

def urgency_to_recommendation(urgency: str, affected_system: Optional[str] = None) -> str:
    """
    Map Phase 3 urgency label to a human-readable maintenance recommendation.
    """
    mapping = {
        "CRITICAL": (
            f"Immediate service required — critical fault detected"
            + (f" in {affected_system}" if affected_system else "")
            + ". Do not operate the vehicle."
        ),
        "HIGH": (
            f"Schedule service within 3 days"
            + (f" — {affected_system} showing elevated risk" if affected_system else "")
            + "."
        ),
        "MEDIUM": (
            f"Service recommended within 7 days"
            + (f" — monitor {affected_system}" if affected_system else "")
            + "."
        ),
        "LOW": "Routine maintenance on schedule. Vehicle is in good health.",
    }
    return mapping.get(urgency.upper(), "Monitor vehicle health and schedule next routine service.")


def maintenance_status_label(book_within_days: int, urgency: str) -> str:
    """Return a short status badge string for the dashboard."""
    if urgency.upper() == "CRITICAL":
        return "CRITICAL — Book Now"
    if book_within_days <= 3:
        return f"Urgent — Book in {book_within_days}d"
    if book_within_days <= 7:
        return f"Soon — Book in {book_within_days}d"
    if book_within_days <= 14:
        return f"Upcoming — Book in {book_within_days}d"
    return "On Schedule"


# ---------------------------------------------------------------------------
# Vehicle-ID helpers
# ---------------------------------------------------------------------------

def vehicle_index(vehicle_id: str) -> int:
    """
    Extract the zero-based integer index from 'Vehicle_XXXX'.
    Returns -1 for unrecognised formats.
    """
    try:
        return int(vehicle_id.split("_")[-1]) - 1
    except (ValueError, IndexError):
        return -1


def format_vehicle_id(index: int) -> str:
    """Format a zero-based index as 'Vehicle_XXXX'."""
    return f"Vehicle_{index + 1:04d}"


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(level: str = "INFO") -> None:
    """Configure root logger for the application."""
    import sys
    from config.settings import LOG_FORMAT
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=LOG_FORMAT,
        stream=sys.stdout,
    )
