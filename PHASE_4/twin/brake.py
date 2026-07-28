"""
twin/brake.py
=============
BrakeTwin — Digital Twin for the vehicle's braking system.

No dedicated brake dataset exists.  Brake health is estimated synthetically
from available vehicle-level proxies.

Synthetic Estimation Methodology
==================================
Assumptions (all documented here):

1. PAD LIFE MODEL
   Assumption : A standard brake pad lasts 40,000 km (BRAKE_INITIAL_PAD_LIFE_KM).
   Source     : Industry standard for mid-range passenger vehicles (BOSCH, 2022).
   Proxy      : Phase 3's Remaining_Useful_Life_KM is used as a mileage surrogate.
                Actual mileage = (max_rul_km − current_rul_km).
   Formula    : pad_wear% = (mileage_km / pad_life_km) × 100, clamped [0, 100].
   Pad health = 100 − pad_wear%.

2. HARD BRAKING EVENTS
   Assumption : High vibration (> 0.5 g) combined with RPM drop > 1000 RPM
                constitutes a simulated hard-braking proxy event.
   Penalty    : 0.05% health deducted per detected event (BRAKE_HARD_BRAKING_PENALTY).
   Rationale  : Hard braking accelerates thermal glazing of pads.

3. THERMAL STRESS
   Assumption : Sustained high engine temperature (> 100°C) correlates with
                excessive brake temperature during mountain / urban driving.
   Penalty    : Linear penalty applied when temp > 100°C.

4. COMPOSITE SCORE
   health = (0.70 × pad_health) + (0.20 × thermal_score) + (0.10 × vibration_score)
   All sub-scores in [0, 100]; final score clamped to [0, 100].

5. FAILURE PROBABILITY
   Derived as : (100 − health) / 100 × 0.35
   Cap of 0.35 because brake failure probability is dominated by pad wear
   (which is well-managed by service intervals) rather than sudden failure.

6. DEGRADATION SIMULATION
   Linear: 0.10% / day (BRAKE_DEGRADATION_RATE_PER_DAY) — faster than engine
   because pad wear is cumulative and non-reversible between service events.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional

import pandas as pd

from config.settings import (
    BRAKE_DEGRADATION_RATE_PER_DAY,
    BRAKE_HARD_BRAKING_PENALTY,
    BRAKE_INITIAL_PAD_LIFE_KM,
    DEFAULT_DEGRADATION_RATES,
    SENSOR_THRESHOLDS,
)
from utils.helpers import classify_health, clamp, utc_now_iso
from utils.models import BrakeState

logger = logging.getLogger(__name__)

MAX_HISTORY_SIZE = 500
_BRAKE_FAILURE_SCALE   = 0.35
_HARD_BRAKE_VIB_THRESH = 0.50   # g — vibration threshold for hard-brake proxy
_THERMAL_STRESS_TEMP   = 100.0  # °C — above this, thermal penalty kicks in


class BrakeTwin:
    """
    Virtual representation of the vehicle's braking system.

    Health is derived synthetically from mileage proxy (RUL_KM), vibration,
    temperature, and fault count.  See module docstring for full methodology.

    Attributes
    ----------
    vehicle_id             : Unique vehicle identifier
    _estimated_mileage_km  : Synthetic mileage derived from RUL_KM delta
    _pad_wear_pct          : Estimated pad wear percentage [0–100]
    _hard_brake_count      : Cumulative proxy hard-braking events
    _health_score          : Composite brake health score [0–100]
    _failure_probability   : Derived failure probability [0–1]
    _health_status         : Categorical label
    _maintenance_rec       : Maintenance recommendation
    _history               : Ring buffer
    _last_updated          : ISO-8601 timestamp
    """

    # Track max RUL seen per vehicle to compute mileage delta
    _max_rul_km_seen: float = 2480.0  # dataset max from Phase 3

    def __init__(self, vehicle_id: str) -> None:
        self.vehicle_id = vehicle_id

        self._estimated_mileage_km: float = 0.0
        self._pad_wear_pct:         float = 0.0
        self._hard_brake_count:     int   = 0

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
        Estimate brake health from proxy sensors in the given data row.

        Parameters
        ----------
        row : Single-vehicle row from the merged Phase 2 + Phase 3 dataset
        """
        rul_km      = float(row.get("Remaining_Useful_Life_KM", 2480.0))
        vibration   = float(row.get("engine_vibration",         0.25))
        temperature = float(row.get("engine_temperature",       80.0))
        rpm         = float(row.get("engine_rpm",               2500.0))
        fault_count = float(row.get("fault_count",              0.0))

        # --- 1. Mileage proxy → pad wear ---
        self._estimated_mileage_km = max(0.0, self._max_rul_km_seen - rul_km)
        self._pad_wear_pct = clamp(
            (self._estimated_mileage_km / BRAKE_INITIAL_PAD_LIFE_KM) * 100.0
        )
        pad_health = clamp(100.0 - self._pad_wear_pct)

        # --- 2. Hard braking detection proxy ---
        if vibration > _HARD_BRAKE_VIB_THRESH and rpm < 1500.0:
            self._hard_brake_count += 1

        # --- 3. Thermal stress sub-score ---
        if temperature <= _THERMAL_STRESS_TEMP:
            thermal_score = 100.0
        else:
            excess = temperature - _THERMAL_STRESS_TEMP
            thermal_score = clamp(100.0 - (excess / (_THERMAL_STRESS_TEMP - 44.5)) * 100.0)

        # --- 4. Vibration sub-score ---
        v_cfg = SENSOR_THRESHOLDS["engine_vibration"]
        vib_score = clamp(
            100.0 - (vibration / v_cfg["max"]) * 100.0
        )

        # --- 5. Composite score ---
        raw = (
            0.70 * pad_health
            + 0.20 * thermal_score
            + 0.10 * vib_score
        )
        # Deduct hard braking penalty (cumulative, capped at 10 events)
        penalty = min(self._hard_brake_count, 10) * BRAKE_HARD_BRAKING_PENALTY
        self._health_score = clamp(raw - penalty * 100.0)

        # --- 6. Failure probability ---
        self._failure_probability = clamp(
            (100.0 - self._health_score) / 100.0 * _BRAKE_FAILURE_SCALE,
            lo=0.0, hi=1.0,
        )

        self._health_status   = classify_health(self._health_score)
        self._maintenance_rec = self._recommend()
        self._last_updated    = utc_now_iso()

        self._history.append(self._snapshot())
        logger.debug("BrakeTwin [%s] updated → health=%.1f, pad_wear=%.1f%%",
                     self.vehicle_id, self._health_score, self._pad_wear_pct)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vehicle_id":                 self.vehicle_id,
            "timestamp":                  self._last_updated,
            "health_score":               round(self._health_score, 2),
            "health_status":              self._health_status,
            "estimated_mileage_km":       round(self._estimated_mileage_km, 1),
            "pad_wear_percentage":        round(self._pad_wear_pct, 2),
            "hard_brake_event_count":     self._hard_brake_count,
            "failure_probability":        round(self._failure_probability, 4),
            "maintenance_recommendation": self._maintenance_rec,
            "history_length":             len(self._history),
        }

    def to_model(self) -> BrakeState:
        return BrakeState(**self.to_dict())

    def simulate(self, days: int, daily_rate: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Project brake health degradation over the given number of days.

        Brake pads wear continuously with use, modelled as linear decay.
        Default rate: 0.10% / day (BRAKE_DEGRADATION_RATE_PER_DAY).
        """
        rate       = daily_rate if daily_rate is not None else BRAKE_DEGRADATION_RATE_PER_DAY
        results    = []
        cur_health = self._health_score
        cur_wear   = self._pad_wear_pct
        base_date  = datetime.now(timezone.utc)

        for day in range(1, days + 1):
            cur_health = clamp(cur_health - rate)
            cur_wear   = clamp(cur_wear   + rate, 0, 100)
            cur_fp     = clamp((100.0 - cur_health) / 100.0 * _BRAKE_FAILURE_SCALE, 0, 1)
            results.append({
                "day":               day,
                "date":              (base_date + timedelta(days=day)).strftime("%Y-%m-%d"),
                "brake_health":      round(cur_health, 2),
                "pad_wear_pct":      round(cur_wear, 2),
                "failure_probability": round(cur_fp, 4),
                "health_status":     classify_health(cur_health),
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
    def pad_wear_percentage(self) -> float:
        return self._pad_wear_pct

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _recommend(self) -> str:
        if self._pad_wear_pct >= 80 or self._health_score < 40:
            return "Replace brake pads immediately. Inspect rotors for scoring."
        if self._pad_wear_pct >= 60 or self._health_score < 65:
            return "Schedule brake pad replacement within 2–3 service visits."
        if self._pad_wear_pct >= 40 or self._health_score < 85:
            return "Brake pads at mid-life. Inspect at next service interval."
        return "Brakes healthy. No action required."

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "timestamp":           self._last_updated,
            "brake_health":        round(self._health_score, 2),
            "pad_wear_pct":        round(self._pad_wear_pct, 2),
            "hard_brake_events":   self._hard_brake_count,
            "failure_probability": round(self._failure_probability, 4),
        }

    def __repr__(self) -> str:
        return (
            f"BrakeTwin(vehicle={self.vehicle_id}, "
            f"health={self._health_score:.1f}, "
            f"pad_wear={self._pad_wear_pct:.1f}%, "
            f"status={self._health_status})"
        )
