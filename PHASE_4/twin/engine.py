"""
twin/engine.py
==============
EngineTwin — Digital Twin for the vehicle's engine subsystem.

Data sources
------------
* Sensor readings  : Phase 2 (temperature, pressure, rpm, vibration)
* Health score     : Phase 2 (engine_health)
* Failure data     : Phase 3 (Failure_Probability, RUL, Top_Risk_Sensor,
                              SHAP_Value, Affected_System, Recommended_Action)

NASA C-MAPSS integration
-------------------------
When C-MAPSS training data is available, the simulation engine uses its
degradation curves to produce physics-informed RUL trajectories.  If the
data directory is missing, the twin falls back to the linear degradation
rate defined in config.settings.DEFAULT_DEGRADATION_RATES["engine"].

History buffer
--------------
The twin stores the last MAX_HISTORY_SIZE update snapshots in a deque.
This is the data source for the Historical Trends dashboard page.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional

import pandas as pd

from config.settings import DEFAULT_DEGRADATION_RATES, SENSOR_THRESHOLDS
from utils.helpers import classify_health, clamp, sensor_sub_score, utc_now_iso
from utils.models import EngineState

logger = logging.getLogger(__name__)

MAX_HISTORY_SIZE = 500


class EngineTwin:
    """
    Virtual representation of a vehicle's engine subsystem.

    Attributes
    ----------
    vehicle_id          : Unique vehicle identifier
    _temperature        : Current engine temperature (°C)
    _pressure           : Current engine pressure (bar)
    _rpm                : Current engine RPM
    _vibration          : Current engine vibration (g)
    _health_score       : Engine health score [0–100]
    _failure_probability: Probability of near-term failure [0–1]
    _rul_cycles         : Estimated remaining useful life in drive cycles
    _rul_km             : Estimated remaining useful life in kilometres
    _maintenance_rec    : Human-readable maintenance recommendation
    _health_status      : Categorical health label
    _top_risk_sensor    : Name of the sensor most contributing to risk
    _shap_explanation   : SHAP-based explanation text
    _affected_system    : Subsystem identified as at risk
    _history            : Ring buffer of historical snapshots
    _last_updated       : ISO-8601 timestamp of last update
    """

    def __init__(self, vehicle_id: str) -> None:
        self.vehicle_id = vehicle_id

        # Sensor values
        self._temperature:   float = 80.0
        self._pressure:      float = 30.0
        self._rpm:           float = 2500.0
        self._vibration:     float = 0.25

        # Health and risk (sourced from Phase 2 / Phase 3)
        self._health_score:        float = 100.0
        self._failure_probability: float = 0.0
        self._rul_cycles:          int   = 120
        self._rul_km:              int   = 2400

        # Recommendations
        self._maintenance_rec:  str           = "No action required"
        self._health_status:    str           = "Excellent"
        self._top_risk_sensor:  Optional[str] = None
        self._shap_explanation: Optional[str] = None
        self._affected_system:  Optional[str] = None

        # History
        self._history: Deque[Dict[str, Any]] = deque(maxlen=MAX_HISTORY_SIZE)
        self._last_updated: str = utc_now_iso()

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def update(self, row: pd.Series) -> None:
        """
        Synchronise the twin with a new data row from the merged DataFrame.

        Parameters
        ----------
        row : A single-vehicle row from the merged Phase 2 + Phase 3 dataset
        """
        self._temperature   = float(row.get("engine_temperature", self._temperature))
        self._pressure      = float(row.get("engine_pressure",    self._pressure))
        self._rpm           = float(row.get("engine_rpm",         self._rpm))
        self._vibration     = float(row.get("engine_vibration",   self._vibration))

        self._health_score        = clamp(float(row.get("engine_health", self._health_score)))
        self._failure_probability = clamp(float(row.get("Failure_Probability", self._failure_probability)), 0, 1)
        self._rul_cycles          = int(row.get("Remaining_Useful_Life_Cycles", self._rul_cycles))
        self._rul_km              = int(row.get("Remaining_Useful_Life_KM", self._rul_km))

        self._top_risk_sensor  = str(row.get("Top_Risk_Sensor", "")) or None
        self._shap_explanation = str(row.get("Reason", "")) or None
        self._affected_system  = str(row.get("Affected_System", "")) or None
        self._maintenance_rec  = str(row.get("Recommended_Action", "No action required"))

        self._health_status = classify_health(self._health_score)
        self._last_updated  = utc_now_iso()

        # Append to history buffer
        self._history.append(self._snapshot())
        logger.debug("EngineTwin [%s] updated → health=%.1f", self.vehicle_id, self._health_score)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise current twin state to a plain dictionary."""
        return {
            "vehicle_id":                   self.vehicle_id,
            "timestamp":                    self._last_updated,
            "temperature":                  round(self._temperature, 2),
            "pressure":                     round(self._pressure, 2),
            "rpm":                          round(self._rpm, 1),
            "vibration":                    round(self._vibration, 4),
            "health_score":                 round(self._health_score, 2),
            "failure_probability":          round(self._failure_probability, 4),
            "remaining_useful_life_cycles": self._rul_cycles,
            "remaining_useful_life_km":     self._rul_km,
            "health_status":                self._health_status,
            "maintenance_recommendation":   self._maintenance_rec,
            "top_risk_sensor":              self._top_risk_sensor,
            "shap_explanation":             self._shap_explanation,
            "affected_system":              self._affected_system,
            "history_length":               len(self._history),
        }

    def to_model(self) -> EngineState:
        """Return a validated Pydantic EngineState model."""
        return EngineState(**self.to_dict())

    def simulate(self, days: int, daily_rate: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Project engine health degradation over the given number of days.

        Uses linear degradation with a daily decay rate.  If a daily_rate
        is passed (e.g. from the NASACMASSEngine simulation), it overrides
        the config default.

        Parameters
        ----------
        days       : Simulation horizon
        daily_rate : Daily health decay (% per day); defaults to config value

        Returns
        -------
        List of dicts, one per day, with projected engine state.
        """
        rate = daily_rate if daily_rate is not None else DEFAULT_DEGRADATION_RATES["engine"]
        results = []
        current_health = self._health_score
        current_rul    = self._rul_cycles
        base_date      = datetime.now(timezone.utc)

        for day in range(1, days + 1):
            current_health = clamp(current_health - rate)
            current_rul    = max(0, current_rul - 1)
            results.append({
                "day":            day,
                "date":           (base_date + timedelta(days=day)).strftime("%Y-%m-%d"),
                "engine_health":  round(current_health, 2),
                "rul_cycles":     current_rul,
                "health_status":  classify_health(current_health),
            })

        return results

    def health_status(self) -> str:
        """Return the categorical health label for this component."""
        return self._health_status

    # ------------------------------------------------------------------
    # History access
    # ------------------------------------------------------------------

    def get_history(self) -> List[Dict[str, Any]]:
        """Return full history buffer as a list of dicts (oldest first)."""
        return list(self._history)

    # ------------------------------------------------------------------
    # Properties (read-only external access)
    # ------------------------------------------------------------------

    @property
    def health_score(self) -> float:
        return self._health_score

    @property
    def failure_probability(self) -> float:
        return self._failure_probability

    @property
    def rul_cycles(self) -> int:
        return self._rul_cycles

    @property
    def rul_km(self) -> int:
        return self._rul_km

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def rpm(self) -> float:
        return self._rpm

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _snapshot(self) -> Dict[str, Any]:
        """Lightweight snapshot stored in the history buffer."""
        return {
            "timestamp":          self._last_updated,
            "engine_health":      round(self._health_score, 2),
            "temperature":        round(self._temperature, 2),
            "pressure":           round(self._pressure, 2),
            "rpm":                round(self._rpm, 1),
            "vibration":          round(self._vibration, 4),
            "failure_probability": round(self._failure_probability, 4),
            "rul_cycles":         self._rul_cycles,
        }

    def __repr__(self) -> str:
        return (
            f"EngineTwin(vehicle={self.vehicle_id}, "
            f"health={self._health_score:.1f}, "
            f"status={self._health_status})"
        )
