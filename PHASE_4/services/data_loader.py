"""
services/data_loader.py
=======================
Responsible for loading, validating, and merging the Phase 2 and Phase 3
CSV outputs into a single unified DataFrame.

Merge logic
-----------
Phase 2 has 2000 rows of time-series sensor readings with no Vehicle_ID.
Phase 3 has 2000 rows keyed on Vehicle_ID (Vehicle_0001 … Vehicle_2000).

We assign Vehicle_ID to Phase 2 by position (row i → Vehicle_{i+1:04d})
and merge on that key.  The result is one row per vehicle containing:
  - raw sensor readings (Phase 2)
  - health scores (Phase 2 + Phase 3)
  - failure predictions, RUL, recommendations (Phase 3)

This merged DataFrame is the single source of truth for all twin instances.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from config.settings import MERGED_CSV, PHASE2_CSV, PHASE3_CSV, SENSOR_COLUMNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assign_vehicle_id(df: pd.DataFrame) -> pd.DataFrame:
    """Add 'Vehicle_ID' column to Phase 2 DataFrame by positional index."""
    df = df.copy()
    df["Vehicle_ID"] = [f"Vehicle_{i + 1:04d}" for i in range(len(df))]
    return df


def _rename_phase2_sensors(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rename raw Phase 2 sensor columns to canonical internal names defined
    in config.settings.SENSOR_COLUMNS.  Unknown columns are left as-is.
    """
    return df.rename(columns=SENSOR_COLUMNS)


def _validate_phase2(df: pd.DataFrame) -> pd.DataFrame:
    """Basic sanity checks on Phase 2 data; fill NaNs with column medians."""
    required = list(SENSOR_COLUMNS.keys()) + [
        "engine_health", "battery_health", "vehicle_health",
        "ml_health_score", "trip_readiness", "health_class",
        "health_class_id", "failure",
    ]
    for col in required:
        canonical = SENSOR_COLUMNS.get(col, col)
        if canonical not in df.columns and col not in df.columns:
            logger.warning("Phase 2 missing expected column: %s", col)

    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())
    return df


def _validate_phase3(df: pd.DataFrame) -> pd.DataFrame:
    """Basic sanity checks on Phase 3 data; fill NaNs sensibly."""
    df = df.copy()
    if "Failure_Probability" in df.columns:
        df["Failure_Probability"] = df["Failure_Probability"].fillna(0.0).clip(0, 1)
    if "Remaining_Useful_Life_Cycles" in df.columns:
        df["Remaining_Useful_Life_Cycles"] = (
            df["Remaining_Useful_Life_Cycles"].fillna(0).astype(int)
        )
    if "Remaining_Useful_Life_KM" in df.columns:
        df["Remaining_Useful_Life_KM"] = (
            df["Remaining_Useful_Life_KM"].fillna(0).astype(int)
        )
    str_cols = [
        "Urgency", "Top_Risk_Sensor", "Affected_System",
        "Recommended_Action", "Reason", "Maintenance_Priority",
    ]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].fillna("N/A")
    return df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_phase2(path: Path = PHASE2_CSV) -> pd.DataFrame:
    """Load and pre-process Phase 2 CSV."""
    logger.info("Loading Phase 2 data from %s", path)
    df = pd.read_csv(path)
    df = _assign_vehicle_id(df)
    df = _rename_phase2_sensors(df)
    df = _validate_phase2(df)
    logger.info("Phase 2 loaded: %d rows, %d columns", len(df), len(df.columns))
    return df


def load_phase3(path: Path = PHASE3_CSV) -> pd.DataFrame:
    """Load and pre-process Phase 3 CSV."""
    logger.info("Loading Phase 3 data from %s", path)
    df = pd.read_csv(path)
    df = _validate_phase3(df)
    logger.info("Phase 3 loaded: %d rows, %d columns", len(df), len(df.columns))
    return df


def merge_phases(
    df2: Optional[pd.DataFrame] = None,
    df3: Optional[pd.DataFrame] = None,
    save: bool = True,
) -> pd.DataFrame:
    """
    Merge Phase 2 and Phase 3 DataFrames on Vehicle_ID.

    Parameters
    ----------
    df2  : Pre-loaded Phase 2 DataFrame (loaded fresh if None)
    df3  : Pre-loaded Phase 3 DataFrame (loaded fresh if None)
    save : If True, write the merged DataFrame to MERGED_CSV for inspection

    Returns
    -------
    pd.DataFrame with one row per vehicle containing all sensor, health,
    and prediction columns.
    """
    if df2 is None:
        df2 = load_phase2()
    if df3 is None:
        df3 = load_phase3()

    # Phase 3 may duplicate some health columns from Phase 2.
    # We keep Phase 3 versions for health metrics (they are the model outputs)
    # and Phase 2 versions for raw sensor readings.
    p3_health_cols = [
        "Engine_Health", "Battery_Health", "Vehicle_Health",
        "ML_Health_Score", "Trip_Readiness",
    ]
    # Drop Phase 3 health columns that duplicate Phase 2 to avoid _x/_y suffixes
    # We keep Phase 2 lowercase versions as the ground truth sensors.
    cols_to_drop = [c for c in p3_health_cols if c in df3.columns]
    df3_slim = df3.drop(columns=cols_to_drop)

    merged = pd.merge(df2, df3_slim, on="Vehicle_ID", how="inner")

    if len(merged) < len(df2):
        logger.warning(
            "Merge lost rows: Phase2=%d, Phase3=%d, Merged=%d. "
            "Check that Vehicle_IDs align.",
            len(df2), len(df3), len(merged),
        )

    # Normalise column name casing for downstream consumers
    merged.columns = [c.strip() for c in merged.columns]

    if save:
        MERGED_CSV.parent.mkdir(parents=True, exist_ok=True)
        merged.to_csv(MERGED_CSV, index=False)
        logger.info("Merged dataset saved to %s", MERGED_CSV)

    logger.info("Merged dataset: %d vehicles, %d columns", len(merged), len(merged.columns))
    return merged


@lru_cache(maxsize=1)
def get_merged_dataframe() -> pd.DataFrame:
    """
    Cached accessor for the merged vehicle DataFrame.
    The cache is populated on first call and reused for all subsequent calls,
    avoiding repeated CSV I/O during the server lifetime.

    To force a reload (e.g. after CSV update), call:
        get_merged_dataframe.cache_clear()
    """
    return merge_phases()


def get_vehicle_row(vehicle_id: str) -> Optional[pd.Series]:
    """
    Retrieve a single vehicle row from the merged DataFrame.

    Parameters
    ----------
    vehicle_id : e.g. 'Vehicle_0001'

    Returns
    -------
    pd.Series or None if not found
    """
    df = get_merged_dataframe()
    matches = df[df["Vehicle_ID"] == vehicle_id]
    if matches.empty:
        return None
    return matches.iloc[0]


def list_vehicle_ids() -> list[str]:
    """Return all Vehicle_IDs in the merged dataset, sorted."""
    df = get_merged_dataframe()
    return sorted(df["Vehicle_ID"].tolist())


def get_fleet_summary() -> dict:
    """Return summary statistics for the full fleet."""
    df = get_merged_dataframe()
    return {
        "total_vehicles":          len(df),
        "mean_vehicle_health":     round(df["vehicle_health"].mean(), 2),
        "mean_engine_health":      round(df["engine_health"].mean(), 2),
        "mean_battery_health":     round(df["battery_health"].mean(), 2),
        "mean_failure_probability": round(df["Failure_Probability"].mean(), 4),
        "critical_vehicles":       int((df["health_class"] == "Critical").sum()),
        "warning_vehicles":        int((df["health_class"] == "Warning").sum()),
        "good_vehicles":           int((df["health_class"] == "Good").sum()),
        "excellent_vehicles":      int((df["health_class"] == "Excellent").sum()),
        "vehicles_needing_service": int((df["Book_Service_Within_Days"] <= 7).sum()),
    }
