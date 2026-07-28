"""
twin/battery.py
===============
BatteryTwin — Digital Twin for the vehicle's 12V lead-acid / Li-ion battery.

Data sources
------------
All data is derived purely from Phase 2 sensor columns and Phase 3 predictions.
The NASA Battery Dataset is NOT required.

Phase 2 columns used:
    battery_voltage      : Terminal voltage (V)
    battery_current      : Discharge/charge current (A)
    battery_temperature  : Cell temperature (°C)
    battery_health       : Composite health score from Phase 2 ML model

Phase 3 columns used:
    Failure_Probability
    Remaining_Useful_Life_Cycles
    Remaining_Useful_Life_KM
    Recommended_Action

State-of-Charge (SOC) estimation
----------------------------------
SOC is estimated from terminal voltage using a simplified Open-Circuit
Voltage (OCV) look-up calibrated to lead-acid / AGM chemistry:

    V_oc ≈ 2.14 × cells  → 12.84 V = 100% SOC
    V_oc ≈ 2.00 × cells  → 12.00 V = 0%  SOC

Linear interpolation between these bounds; clamped to [0, 100].

State-of-Health (SOH) estimation
-----------------------------------
SOH is proxied directly from battery_health (Phase 2), which was computed
by the Phase 2 ML model using voltage, current, and temperature features.
SOH = battery_health (already in [0, 100]).
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional

import pandas as pd

from config.settings import DEFAULT_DEGRADATION_RATES, SENSOR_THRESHOLDS
from utils.helpers import classify_health, clamp, utc_now_iso
from utils.models import BatteryState

logger = logging.getLogger(__name__)

MAX_HISTORY_SIZE = 500

# OCV–SOC calibration constants (12V lead-acid / AGM)
_SOC_V_MAX = 12.84   # 100% SOC voltage
_SOC_V_MIN = 12.00   # 0%   SOC voltage


def _estimate_soc(voltage: float) -> float:
    """Linear OCV–SOC mapping; clamped to [0, 100]."""
    soc = (voltage - _SOC_V_MIN) / (_SOC_V_MAX - _SOC_V_MIN) * 100.0
    return clamp(soc)


class BatteryTwin:
    """
    Virtual representation of the vehicle's battery subsystem.

    All health intelligence is sourced from Phase 2 and Phase 3 outputs.
    No retraining of ML models occurs here.

    Attributes
    ----------
    vehicle_id           : Unique vehicle identifier
    _voltage             : Battery terminal voltage (V)
    _current             : Battery current (A); positive = discharge
    _temperature         : Battery cell temperature (°C)
    _health_score        : Phase 2 battery_health [0–100]
    _failure_probability : Phase 3 failure probability [0–1]
    _rul_cycles          : Remaining useful life in drive cycles
    _rul_km              : Remaining useful life in km
    _soc                 : State of Charge estimate [0–100]
    _soh                 : State of Health (= battery_health) [0–100]
    _health_status       : Categorical label (Excellent/Good/Warning/Critical)
    _maintenance_rec     : Maintenance recommendation
    _history             : Ring buffer of past snapshots
    _last_updated        : ISO-8601 timestamp
    """

    def __init__(self, vehicle_id: str) -> None:
        self.vehicle_id = vehicle_id

        self._voltage:      float = 12.4
        self._current:      float = 50.0
        self._temperature:  float = 35.0

        self._health_score:        float = 100.0
        self._failure_probability: float = 0.0
        self._rul_cycles:          int   = 120
        self._rul_km:              int   = 2400

        self._soc: float = 80.0
        self._soh: float = 100.0

        self._health_status:   str = "Excellent"
        self._maintenance_rec: str = "No action required"

        self._history: Deque[Dict[str, Any]] = deque(maxlen=MAX_HISTORY_SIZE)
        self._last_updated: str = utc_now_iso()

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def update(self, row: pd.Series) -> None:
        """
        Synchronise the twin with a data row from the merged DataFrame.

        Parameters
        ----------
        row : Single-vehicle row from the merged Phase 2 + Phase 3 dataset
        """
        self._voltage      = float(row.get("battery_voltage",     self._voltage))
        self._current      = float(row.get("battery_current",     self._current))
        self._temperature  = float(row.get("battery_temperature", self._temperature))

        self._health_score        = clamp(float(row.get("battery_health",           self._health_score)))
        self._failure_probability = clamp(float(row.get("Failure_Probability",      self._failure_probability)), 0, 1)
        self._rul_cycles          = int(row.get("Remaining_Useful_Life_Cycles",     self._rul_cycles))
        self._rul_km              = int(row.get("Remaining_Useful_Life_KM",         self._rul_km))
        self._maintenance_rec     = str(row.get("Recommended_Action", "No action required"))

        # Derived estimates
        self._soc = _estimate_soc(self._voltage)
        self._soh = self._health_score   # proxy: Phase 2 battery_health = SOH

        self._health_status = classify_health(self._health_score)
        self._last_updated  = utc_now_iso()

        self._history.append(self._snapshot())
        logger.debug("BatteryTwin [%s] updated → health=%.1f, SOC=%.1f%%",
                     self.vehicle_id, self._health_score, self._soc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vehicle_id":                   self.vehicle_id,
            "timestamp":                    self._last_updated,
            "voltage":                      round(self._voltage, 3),
            "current":                      round(self._current, 2),
            "temperature":                  round(self._temperature, 2),
            "health_score":                 round(self._health_score, 2),
            "failure_probability":          round(self._failure_probability, 4),
            "remaining_useful_life_cycles": self._rul_cycles,
            "remaining_useful_life_km":     self._rul_km,
            "state_of_charge":              round(self._soc, 1),
            "state_of_health":              round(self._soh, 1),
            "health_status":                self._health_status,
            "maintenance_recommendation":   self._maintenance_rec,
            "history_length":               len(self._history),
        }

    def to_model(self) -> BatteryState:
        return BatteryState(**self.to_dict())

    def simulate(self, days: int, daily_rate: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Project battery health degradation over the given number of days.

        Battery degradation is modelled as a combination of:
        1. Calendar aging : linear decay at daily_rate (default 0.03% / day)
        2. SOC drift      : voltage decreases ~0.005 V / day as capacity fades
        """
        rate      = daily_rate if daily_rate is not None else DEFAULT_DEGRADATION_RATES["battery"]
        results   = []
        cur_health  = self._health_score
        cur_soh     = self._soh
        cur_soc     = self._soc
        cur_voltage = self._voltage
        cur_rul     = self._rul_cycles
        base_date   = datetime.now(timezone.utc)

        for day in range(1, days + 1):
            cur_health  = clamp(cur_health  - rate)
            cur_soh     = clamp(cur_soh     - rate)
            cur_voltage = max(11.0, cur_voltage - 0.005)
            cur_soc     = _estimate_soc(cur_voltage)
            cur_rul     = max(0, cur_rul - 1)
            results.append({
                "day":             day,
                "date":            (base_date + timedelta(days=day)).strftime("%Y-%m-%d"),
                "battery_health":  round(cur_health, 2),
                "state_of_health": round(cur_soh, 2),
                "state_of_charge": round(cur_soc, 1),
                "voltage":         round(cur_voltage, 3),
                "rul_cycles":      cur_rul,
                "health_status":   classify_health(cur_health),
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

    @property
    def rul_cycles(self) -> int:
        return self._rul_cycles

    @property
    def rul_km(self) -> int:
        return self._rul_km

    @property
    def voltage(self) -> float:
        return self._voltage

    @property
    def soc(self) -> float:
        return self._soc

    @property
    def soh(self) -> float:
        return self._soh

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "timestamp":           self._last_updated,
            "battery_health":      round(self._health_score, 2),
            "voltage":             round(self._voltage, 3),
            "current":             round(self._current, 2),
            "temperature":         round(self._temperature, 2),
            "soc":                 round(self._soc, 1),
            "soh":                 round(self._soh, 1),
            "failure_probability": round(self._failure_probability, 4),
            "rul_cycles":          self._rul_cycles,
        }

    def __repr__(self) -> str:
        return (
            f"BatteryTwin(vehicle={self.vehicle_id}, "
            f"health={self._health_score:.1f}, "
            f"SOC={self._soc:.1f}%, "
            f"status={self._health_status})"
        )
