"""
twin/fuel.py
============
FuelTwin — Digital Twin for the vehicle's fuel system.

No dedicated fuel dataset exists, so Fuel Health is derived from available
engine sensor readings using a transparent, documented scoring algorithm.

Fuel Health Scoring Algorithm
==============================
Rationale: Engine sensor values are strong proxies for fuel system health
because the fuel system's job is to supply the correct air-fuel mixture
to the combustion chamber.  Deviations in temperature, pressure, RPM,
and vibration all signal fuel delivery problems.

Score = Σ (weight_i × sub_score_i)   where sub_scores are in [0, 100]

Factor weights (config.settings.FUEL_HEALTH_WEIGHTS):
┌──────────────────────┬────────┬──────────────────────────────────────────────────┐
│ Factor               │ Weight │ Rationale                                        │
├──────────────────────┼────────┼──────────────────────────────────────────────────┤
│ temperature_factor   │  0.30  │ High engine temp → fuel vapour lock / lean burn  │
│ pressure_factor      │  0.25  │ Low manifold pressure → lean mixture, misfire    │
│ rpm_factor           │  0.20  │ Sustained high RPM → excess fuel consumption     │
│ vibration_factor     │  0.15  │ High vibration → injector nozzle wear proxy      │
│ fault_factor         │  0.10  │ Active DTCs → ECU-detected fuel delivery faults  │
└──────────────────────┴────────┴──────────────────────────────────────────────────┘

Sub-score computation (piecewise linear, see utils.helpers.sensor_sub_score):
  - Optimal operating range → sub_score = 100
  - Linear decay toward critical threshold → sub_score → 0

Failure probability is derived proportionally:
    fuel_failure_probability = (100 - health_score) / 100 × scale_factor
where scale_factor caps the maximum fuel-only failure probability at 0.4
(fuel issues contribute to but rarely cause sudden catastrophic failure alone).
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional

import pandas as pd

from config.settings import (
    DEFAULT_DEGRADATION_RATES,
    FUEL_DEGRADATION_RATE_PER_DAY,
    FUEL_HEALTH_WEIGHTS,
    SENSOR_THRESHOLDS,
)
from utils.helpers import classify_health, clamp, sensor_sub_score, utc_now_iso
from utils.models import FuelState

logger = logging.getLogger(__name__)

MAX_HISTORY_SIZE = 500
_FUEL_FAILURE_SCALE = 0.40  # max contribution of fuel to failure probability


class FuelTwin:
    """
    Virtual representation of the vehicle's fuel delivery system.

    Health is computed on every update() call from engine sensor readings.
    All scoring logic is deterministic and documented above.

    Attributes
    ----------
    vehicle_id          : Unique vehicle identifier
    _temperature_contrib : Temperature sub-score [0–100]
    _pressure_contrib   : Pressure sub-score [0–100]
    _rpm_contrib        : RPM sub-score [0–100]
    _vibration_contrib  : Vibration sub-score [0–100]
    _fault_contrib      : Fault-count sub-score [0–100]
    _health_score       : Weighted composite score [0–100]
    _failure_probability: Derived failure probability [0–1]
    _health_status      : Categorical label
    _maintenance_rec    : Maintenance recommendation
    _history            : Ring buffer
    _last_updated       : ISO-8601 timestamp
    """

    def __init__(self, vehicle_id: str) -> None:
        self.vehicle_id = vehicle_id

        self._temperature_contrib: float = 100.0
        self._pressure_contrib:    float = 100.0
        self._rpm_contrib:         float = 100.0
        self._vibration_contrib:   float = 100.0
        self._fault_contrib:       float = 100.0

        self._health_score:        float = 100.0
        self._failure_probability: float = 0.0
        self._health_status:       str   = "Excellent"
        self._maintenance_rec:     str   = "No action required"

        self._history: Deque[Dict[str, Any]] = deque(maxlen=MAX_HISTORY_SIZE)
        self._last_updated: str = utc_now_iso()

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def update(self, row: pd.Series) -> None:
        """
        Compute Fuel Health from engine sensor readings in the given row.

        Parameters
        ----------
        row : Single-vehicle row from the merged Phase 2 + Phase 3 dataset
        """
        temp      = float(row.get("engine_temperature", 84.0))
        pressure  = float(row.get("engine_pressure",    30.0))
        rpm       = float(row.get("engine_rpm",         2500.0))
        vibration = float(row.get("engine_vibration",   0.25))
        faults    = float(row.get("fault_count",        0.0))

        # --- Sub-score computation ---
        t_cfg = SENSOR_THRESHOLDS["engine_temperature"]
        self._temperature_contrib = sensor_sub_score(
            temp,
            optimal_low=t_cfg["optimal_low"],
            optimal_high=t_cfg["optimal_high"],
            max_val=t_cfg["max"],
            critical=t_cfg["critical"],
        )

        p_cfg = SENSOR_THRESHOLDS["engine_pressure"]
        self._pressure_contrib = sensor_sub_score(
            pressure,
            optimal_low=p_cfg["optimal_low"],
            optimal_high=p_cfg["optimal_high"],
            max_val=p_cfg["max"],
            critical=p_cfg["critical"],
        )

        r_cfg = SENSOR_THRESHOLDS["engine_rpm"]
        self._rpm_contrib = sensor_sub_score(
            rpm,
            optimal_low=r_cfg["optimal_low"],
            optimal_high=r_cfg["optimal_high"],
            max_val=r_cfg["max"],
            critical=r_cfg["critical"],
        )

        v_cfg = SENSOR_THRESHOLDS["engine_vibration"]
        self._vibration_contrib = sensor_sub_score(
            vibration,
            optimal_low=v_cfg["optimal_low"],
            optimal_high=v_cfg["optimal_high"],
            max_val=v_cfg["max"],
            critical=v_cfg["critical"],
        )

        f_cfg = SENSOR_THRESHOLDS["fault_count"]
        self._fault_contrib = sensor_sub_score(
            faults,
            optimal_low=f_cfg["optimal_low"],
            optimal_high=f_cfg["optimal_high"],
            max_val=f_cfg["max"],
            critical=f_cfg["critical"],
        )

        # --- Weighted composite ---
        w = FUEL_HEALTH_WEIGHTS
        self._health_score = clamp(
            w["temperature_factor"] * self._temperature_contrib
            + w["pressure_factor"]  * self._pressure_contrib
            + w["rpm_factor"]       * self._rpm_contrib
            + w["vibration_factor"] * self._vibration_contrib
            + w["fault_factor"]     * self._fault_contrib
        )

        # --- Derived failure probability ---
        self._failure_probability = clamp(
            (100.0 - self._health_score) / 100.0 * _FUEL_FAILURE_SCALE,
            lo=0.0, hi=1.0,
        )

        self._health_status   = classify_health(self._health_score)
        self._maintenance_rec = self._recommend()
        self._last_updated    = utc_now_iso()

        self._history.append(self._snapshot())
        logger.debug("FuelTwin [%s] updated → health=%.1f, status=%s",
                     self.vehicle_id, self._health_score, self._health_status)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vehicle_id":                   self.vehicle_id,
            "timestamp":                    self._last_updated,
            "health_score":                 round(self._health_score, 2),
            "health_status":                self._health_status,
            "temperature_contribution":     round(self._temperature_contrib, 2),
            "pressure_contribution":        round(self._pressure_contrib, 2),
            "rpm_contribution":             round(self._rpm_contrib, 2),
            "vibration_contribution":       round(self._vibration_contrib, 2),
            "fault_contribution":           round(self._fault_contrib, 2),
            "failure_probability":          round(self._failure_probability, 4),
            "maintenance_recommendation":   self._maintenance_rec,
            "history_length":               len(self._history),
        }

    def to_model(self) -> FuelState:
        return FuelState(**self.to_dict())

    def simulate(self, days: int, daily_rate: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Project fuel system health degradation over the given number of days.

        Fuel systems degrade faster than the engine due to:
        - Injector fouling (primary driver)
        - Fuel filter clogging
        - Fuel pump wear

        Default rate: 0.08% / day (configurable via FUEL_DEGRADATION_RATE_PER_DAY).
        """
        rate      = daily_rate if daily_rate is not None else FUEL_DEGRADATION_RATE_PER_DAY
        results   = []
        cur_health = self._health_score
        base_date  = datetime.now(timezone.utc)

        for day in range(1, days + 1):
            cur_health = clamp(cur_health - rate)
            cur_fp     = clamp((100.0 - cur_health) / 100.0 * _FUEL_FAILURE_SCALE, 0, 1)
            results.append({
                "day":           day,
                "date":          (base_date + timedelta(days=day)).strftime("%Y-%m-%d"),
                "fuel_health":   round(cur_health, 2),
                "failure_probability": round(cur_fp, 4),
                "health_status": classify_health(cur_health),
            })

        return results

    def health_status(self) -> str:
        return self._health_status

    # ------------------------------------------------------------------
    # History access
    # ------------------------------------------------------------------

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def health_score(self) -> float:
        return self._health_score

    @property
    def failure_probability(self) -> float:
        return self._failure_probability

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _recommend(self) -> str:
        if self._health_score < 40:
            return "Fuel system inspection required. Check injectors, fuel pump, and filter."
        if self._health_score < 65:
            return "Schedule fuel system service. Consider injector cleaning."
        if self._health_score < 85:
            return "Fuel system nominal. Replace fuel filter at next service interval."
        return "Fuel system healthy. No action required."

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "timestamp":              self._last_updated,
            "fuel_health":            round(self._health_score, 2),
            "temperature_contrib":    round(self._temperature_contrib, 2),
            "pressure_contrib":       round(self._pressure_contrib, 2),
            "rpm_contrib":            round(self._rpm_contrib, 2),
            "vibration_contrib":      round(self._vibration_contrib, 2),
            "fault_contrib":          round(self._fault_contrib, 2),
            "failure_probability":    round(self._failure_probability, 4),
        }

    def __repr__(self) -> str:
        return (
            f"FuelTwin(vehicle={self.vehicle_id}, "
            f"health={self._health_score:.1f}, "
            f"status={self._health_status})"
        )
