"""
services/state_estimator.py
============================
StateEstimator — Pre-processes and enriches a raw merged data row before
it is forwarded to the twin components.

Responsibilities
----------------
1. Validate and clamp sensor readings to physically plausible ranges.
2. Compute derived signals (SOC, fuel efficiency proxy, etc.).
3. Flag anomalous readings for dashboard highlighting.
4. Return an enriched pandas Series ready for twin.update().

Design note
-----------
The StateEstimator is intentionally stateless — it operates on one row
at a time and produces a new row with additional derived columns.  This
makes it trivial to swap in a streaming data source (Kafka, MQTT) later
without changing the twin layer.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

from config.settings import SENSOR_THRESHOLDS
from utils.helpers import clamp, classify_health

logger = logging.getLogger(__name__)


class StateEstimator:
    """
    Stateless sensor validation and signal enrichment layer.

    All methods are pure functions (no side effects on internal state).
    """

    # Anomaly detection thresholds — z-score above this is flagged
    _ANOMALY_ZSCORE = 3.0

    def __init__(self) -> None:
        # Running statistics for z-score anomaly detection (updated per batch)
        self._col_means: Dict[str, float] = {}
        self._col_stds:  Dict[str, float] = {}

    def fit(self, df: pd.DataFrame) -> None:
        """
        Compute column statistics from the full fleet DataFrame.
        Called once during Synchronizer initialisation.

        Parameters
        ----------
        df : Merged vehicle DataFrame (all vehicles)
        """
        numeric = df.select_dtypes(include="number")
        self._col_means = numeric.mean().to_dict()
        self._col_stds  = numeric.std().fillna(1.0).to_dict()
        logger.info("StateEstimator fitted on %d vehicles, %d numeric columns",
                    len(df), len(self._col_means))

    def enrich(self, row: pd.Series) -> pd.Series:
        """
        Validate, clamp, and enrich a single vehicle data row.

        Enrichments added
        -----------------
        * `engine_stress_index`   : composite stress score [0–100]
        * `battery_soc_est`       : estimated State-of-Charge [0–100]
        * `anomaly_flags`         : comma-separated list of flagged sensors
        * `data_quality_score`    : percentage of sensors within normal range

        Parameters
        ----------
        row : Raw merged data row (pd.Series)

        Returns
        -------
        pd.Series with additional derived columns
        """
        row = row.copy()

        # 1 — Clamp sensor readings to physical bounds
        row = self._clamp_sensors(row)

        # 2 — Compute engine stress index
        row["engine_stress_index"] = self._engine_stress(row)

        # 3 — Estimate battery SOC
        row["battery_soc_est"] = self._estimate_soc(float(row.get("battery_voltage", 12.4)))

        # 4 — Anomaly detection
        flags, quality = self._detect_anomalies(row)
        row["anomaly_flags"]       = ",".join(flags) if flags else "none"
        row["data_quality_score"]  = quality

        return row

    # ------------------------------------------------------------------
    # Internal sub-routines
    # ------------------------------------------------------------------

    def _clamp_sensors(self, row: pd.Series) -> pd.Series:
        """Clamp each sensor to its configured physical range."""
        clamp_map = {
            "engine_temperature": (
                SENSOR_THRESHOLDS["engine_temperature"]["min"],
                SENSOR_THRESHOLDS["engine_temperature"]["max"],
            ),
            "engine_pressure": (
                SENSOR_THRESHOLDS["engine_pressure"]["min"],
                SENSOR_THRESHOLDS["engine_pressure"]["max"],
            ),
            "engine_rpm": (
                SENSOR_THRESHOLDS["engine_rpm"]["min"],
                SENSOR_THRESHOLDS["engine_rpm"]["max"],
            ),
            "engine_vibration": (
                SENSOR_THRESHOLDS["engine_vibration"]["min"],
                SENSOR_THRESHOLDS["engine_vibration"]["max"],
            ),
            "battery_voltage": (
                SENSOR_THRESHOLDS["battery_voltage"]["min"],
                SENSOR_THRESHOLDS["battery_voltage"]["max"],
            ),
            "battery_current": (
                SENSOR_THRESHOLDS["battery_current"]["min"],
                SENSOR_THRESHOLDS["battery_current"]["max"],
            ),
            "battery_temperature": (
                SENSOR_THRESHOLDS["battery_temperature"]["min"],
                SENSOR_THRESHOLDS["battery_temperature"]["max"],
            ),
        }
        for col, (lo, hi) in clamp_map.items():
            if col in row.index:
                row[col] = clamp(float(row[col]), lo, hi)
        return row

    def _engine_stress(self, row: pd.Series) -> float:
        """
        Composite engine stress index [0–100].

        High stress = high temperature + high RPM + high vibration.
        Formula: stress = 0.4*T_norm + 0.35*RPM_norm + 0.25*Vib_norm
        where each norm maps the sensor to [0, 100] with 0 = optimal.
        """
        t_cfg  = SENSOR_THRESHOLDS["engine_temperature"]
        r_cfg  = SENSOR_THRESHOLDS["engine_rpm"]
        v_cfg  = SENSOR_THRESHOLDS["engine_vibration"]

        temp  = float(row.get("engine_temperature", 84.0))
        rpm   = float(row.get("engine_rpm",         2500.0))
        vib   = float(row.get("engine_vibration",   0.25))

        t_norm   = clamp((temp - t_cfg["optimal_high"]) / (t_cfg["max"] - t_cfg["optimal_high"]) * 100.0) if temp > t_cfg["optimal_high"] else 0.0
        rpm_norm = clamp((rpm  - r_cfg["optimal_high"]) / (r_cfg["max"] - r_cfg["optimal_high"]) * 100.0) if rpm  > r_cfg["optimal_high"] else 0.0
        vib_norm = clamp(vib / v_cfg["max"] * 100.0)

        return round(0.40 * t_norm + 0.35 * rpm_norm + 0.25 * vib_norm, 2)

    def _estimate_soc(self, voltage: float) -> float:
        """Linear OCV–SOC: 12.84 V = 100%, 12.00 V = 0%."""
        soc = (voltage - 12.00) / (12.84 - 12.00) * 100.0
        return round(clamp(soc), 1)

    def _detect_anomalies(self, row: pd.Series) -> Tuple[list[str], float]:
        """
        Z-score anomaly detection against fleet statistics.

        Returns
        -------
        flags   : list of column names with |z| > threshold
        quality : fraction of sensors within normal range [0–100]
        """
        if not self._col_means:
            return [], 100.0

        sensor_cols = [
            "engine_temperature", "engine_pressure", "engine_rpm",
            "engine_vibration", "battery_voltage", "battery_current",
            "battery_temperature", "fault_count",
        ]
        flags = []
        checked = 0
        for col in sensor_cols:
            if col not in row.index or col not in self._col_means:
                continue
            checked += 1
            std = self._col_stds.get(col, 1.0) or 1.0
            z = abs((float(row[col]) - self._col_means[col]) / std)
            if z > self._ANOMALY_ZSCORE:
                flags.append(col)

        quality = round((1.0 - len(flags) / max(checked, 1)) * 100.0, 1)
        return flags, quality

    def enrich_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply enrich() to every row in a DataFrame."""
        return df.apply(self.enrich, axis=1)
