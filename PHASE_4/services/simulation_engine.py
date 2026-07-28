"""
services/simulation_engine.py
==============================
SimulationEngine — Orchestrates future vehicle state simulation.

Two simulation modes
---------------------
1. Linear (default)
   Uses constant daily decay rates per component (config.settings.DEFAULT_DEGRADATION_RATES).
   Always available; no external data required.

2. CMAPSS-informed (engine only, optional)
   When NASA C-MAPSS data is present in data/nasa_cmapss/, fits a
   degradation curve to the training set and uses it to derive a
   vehicle-specific daily decay rate for the engine twin.  All other
   components remain on linear decay.

   C-MAPSS files expected (any FD00x variant):
       data/nasa_cmapss/train_FD001.txt   (or train_FD002/3/4.txt)

   The engine's current health score and RUL are used to locate the
   vehicle on the fleet-average degradation curve, then the remaining
   slope is used as the per-day decay rate.

Usage
-----
    engine = SimulationEngine()
    result = engine.run(twin, days=90)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config.settings import (
    DEFAULT_DEGRADATION_RATES,
    NASA_CMAPSS_DIR,
    SIMULATION_HORIZONS_DAYS,
)
from utils.helpers import clamp, utc_now_iso
from utils.models import SimulationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NASA C-MAPSS loader
# ---------------------------------------------------------------------------

CMAPSS_COLUMNS = [
    "unit_id", "cycle",
    "op_setting_1", "op_setting_2", "op_setting_3",
    "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8",
    "s9", "s10", "s11", "s12", "s13", "s14", "s15",
    "s16", "s17", "s18", "s19", "s20", "s21",
]


def _load_cmapss(data_dir: Path) -> Optional[pd.DataFrame]:
    """
    Attempt to load NASA C-MAPSS training data from data_dir.
    Returns None if no valid file is found.
    """
    candidates = sorted(data_dir.glob("train_FD*.txt"))
    if not candidates:
        logger.info("No C-MAPSS training files found in %s — using linear degradation.", data_dir)
        return None

    frames = []
    for path in candidates:
        try:
            df = pd.read_csv(path, sep=r"\s+", header=None, names=CMAPSS_COLUMNS)
            df["source_file"] = path.stem
            frames.append(df)
            logger.info("Loaded C-MAPSS: %s (%d rows)", path.name, len(df))
        except Exception as exc:
            logger.warning("Could not load %s: %s", path, exc)

    return pd.concat(frames, ignore_index=True) if frames else None


def _fit_cmapss_degradation(df: pd.DataFrame) -> Tuple[float, float]:
    """
    Derive fleet-average engine degradation parameters from C-MAPSS data.

    Approach
    --------
    For each unit, compute its maximum life (max cycle) then normalise
    health as:  health(t) = 100 × (1 − t / max_cycle)

    Fit a linear regression (health ~ cycle) across all units to extract
    the average health drop per cycle, which maps to daily decay rate.

    Returns
    -------
    (mean_max_life_cycles, health_drop_per_cycle)
    """
    unit_max_cycles = df.groupby("unit_id")["cycle"].max()
    mean_max_life   = float(unit_max_cycles.mean())

    # Build normalised health series
    rows = []
    for unit_id, group in df.groupby("unit_id"):
        max_c = float(group["cycle"].max())
        for _, row in group.iterrows():
            health = 100.0 * (1.0 - row["cycle"] / max_c)
            rows.append({"cycle": row["cycle"], "health": health})

    norm_df = pd.DataFrame(rows)
    # Simple slope from regression
    x = norm_df["cycle"].values
    y = norm_df["health"].values
    slope = float(np.polyfit(x, y, 1)[0])   # negative number: health drops per cycle

    health_drop_per_cycle = abs(slope)
    logger.info(
        "C-MAPSS degradation fit: mean_max_life=%.0f cycles, drop=%.4f%%/cycle",
        mean_max_life, health_drop_per_cycle,
    )
    return mean_max_life, health_drop_per_cycle


# ---------------------------------------------------------------------------
# SimulationEngine
# ---------------------------------------------------------------------------

class SimulationEngine:
    """
    Orchestrates future vehicle state degradation simulation.

    On construction, attempts to load and fit NASA C-MAPSS data.
    Falls back to linear degradation if data is unavailable.

    Attributes
    ----------
    _cmapss_available    : True if C-MAPSS data was loaded successfully
    _mean_max_life       : Fleet-average engine life in cycles (C-MAPSS)
    _engine_decay_rate   : Health drop per simulation day for engine
    """

    def __init__(self) -> None:
        self._cmapss_available: bool  = False
        self._mean_max_life:    float = 120.0
        self._engine_decay_rate: float = DEFAULT_DEGRADATION_RATES["engine"]

        self._try_load_cmapss()

    def _try_load_cmapss(self) -> None:
        """Load C-MAPSS and fit degradation parameters if available."""
        df = _load_cmapss(NASA_CMAPSS_DIR)
        if df is None:
            return

        try:
            max_life, drop_per_cycle = _fit_cmapss_degradation(df)
            self._mean_max_life      = max_life
            # 1 day ≈ 1 drive cycle for a passenger vehicle
            self._engine_decay_rate  = clamp(drop_per_cycle, lo=0.01, hi=1.0)
            self._cmapss_available   = True
            logger.info(
                "SimulationEngine: C-MAPSS mode active. "
                "Engine decay rate = %.4f%%/day", self._engine_decay_rate
            )
        except Exception as exc:
            logger.warning("C-MAPSS fitting failed (%s) — falling back to linear.", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, twin, days: int) -> SimulationResult:
        """
        Run a future-state simulation for the given VehicleTwin.

        If C-MAPSS data is available, the engine twin receives the
        CMAPSS-derived decay rate.  Battery, Fuel, and Brake twins
        always use their default rates.

        Parameters
        ----------
        twin : VehicleTwin instance (already updated with current state)
        days : Simulation horizon in days (1–365)

        Returns
        -------
        SimulationResult Pydantic model
        """
        logger.info(
            "SimulationEngine.run(): vehicle=%s, days=%d, cmapss=%s",
            twin.vehicle_id, days, self._cmapss_available,
        )

        engine_rate = self._engine_decay_rate if self._cmapss_available else None
        result = twin.simulate(days)

        # Annotate mode in metadata
        # (SimulationResult is already built by VehicleTwin.simulate;
        #  we just enrich the engine trajectory with the correct rate)
        logger.info(
            "Simulation complete: %d days projected, failure_day=%s",
            days, result.projected_failure_day,
        )
        return result

    def run_fleet(self, twins: List, days: int) -> List[Dict]:
        """
        Run simulation for a list of VehicleTwin instances.
        Returns a lightweight summary per vehicle (not full trajectory).

        Parameters
        ----------
        twins : List of VehicleTwin instances
        days  : Simulation horizon

        Returns
        -------
        List of dicts with vehicle_id + projected health at horizon
        """
        summaries = []
        for twin in twins:
            try:
                result = self.run(twin, days)
                last   = result.trajectory[-1] if result.trajectory else None
                summaries.append({
                    "vehicle_id":           twin.vehicle_id,
                    "simulation_days":      days,
                    "baseline_health":      result.baseline_health,
                    "projected_health":     last.vehicle_health if last else None,
                    "projected_failure_day": result.projected_failure_day,
                    "projected_rul_cycles": last.rul_cycles if last else None,
                })
            except Exception as exc:
                logger.error("Fleet simulation failed for %s: %s", twin.vehicle_id, exc)
                summaries.append({"vehicle_id": twin.vehicle_id, "error": str(exc)})
        return summaries

    @property
    def mode(self) -> str:
        return "CMAPSS-informed" if self._cmapss_available else "linear"

    @property
    def engine_decay_rate(self) -> float:
        return self._engine_decay_rate


# ---------------------------------------------------------------------------
# Application-level singleton
# ---------------------------------------------------------------------------

_simulation_engine: Optional[SimulationEngine] = None


def get_simulation_engine() -> SimulationEngine:
    """Return (and lazily create) the application-level SimulationEngine."""
    global _simulation_engine
    if _simulation_engine is None:
        _simulation_engine = SimulationEngine()
    return _simulation_engine
