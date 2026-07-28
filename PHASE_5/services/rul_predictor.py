"""
Remaining Useful Life (RUL) Predictor  –  NASA C-MAPSS FD001
=============================================================
XGBoost regressor trained on NASA Turbofan Engine Degradation Dataset.

Sensor-RUL correlations from training data (FD001):
  Sensors that INCREASE with degradation (negative RUL corr):
    s2, s3, s4, s8, s9, s11, s13, s15, s17  → map to temperature/pressure rises
  Sensors that DECREASE with degradation (positive RUL corr):
    s7, s12, s14, s20, s21  → map to efficiency / health metrics

Vehicle parameter mapping uses actual sensor min/max ranges from FD001 training
data so predictions sit firmly in-distribution.
"""

from __future__ import annotations
import os
import numpy as np
import joblib

_MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')
_MAX_RUL   = 125   # cap used during training

# Actual sensor value ranges from FD001 training data
_SENSOR_RANGES = {
    's2':  (641.21, 644.53),   # fan inlet temperature  — rises with degradation
    's3':  (1571.04, 1616.91), # LPC outlet temperature — rises with degradation
    's4':  (1382.25, 1441.49), # HPC outlet temperature — rises with degradation
    's7':  (549.85, 556.06),   # HPC outlet pressure    — drops with degradation
    's8':  (2387.90, 2388.56), # physical fan speed      — rises with degradation
    's9':  (9021.73, 9244.59), # physical core speed     — rises with degradation
    's11': (46.85,   48.53),   # HPC outlet temp ratio   — rises with degradation
    's12': (518.69,  523.38),  # fuel flow ratio         — drops with degradation
    's13': (2387.88, 2388.56), # corrected fan speed     — rises with degradation
    's14': (8099.94, 8293.72), # corrected core speed    — drops with degradation
    's15': (8.325,   8.585),   # bypass ratio            — rises with degradation
    's17': (388.00,  400.00),  # bleed enthalpy          — rises with degradation
    's20': (38.14,   39.43),   # HPT efficiency          — drops with degradation
    's21': (22.89,   23.62),   # LPT efficiency          — drops with degradation
}

_RISK_BANDS = [
    (90, 'Healthy'),
    (50, 'Fair'),
    (20, 'Degraded'),
    (0,  'Critical'),
]


class RULPredictor:
    """
    Predicts remaining useful life in equivalent operating cycles.

    Vehicle-mode maps (rpm, temperature, torque, tool_wear, failure_prob)
    to NASA C-MAPSS FD001 sensor space using calibrated linear interpolation
    within actual training-data ranges.
    """

    def __init__(self):
        self._model    = joblib.load(os.path.join(_MODEL_DIR, 'nasa_rul_xgb.pkl'))
        self._features = joblib.load(os.path.join(_MODEL_DIR, 'nasa_features.pkl'))
        self._sensors  = joblib.load(os.path.join(_MODEL_DIR, 'nasa_sensor_cols.pkl'))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict_from_vehicle(
        self,
        rpm:          float = 1500.0,
        temperature:  float = 310.0,   # K  (process / coolant temperature)
        torque:       float = 40.0,    # Nm
        tool_wear:    float = 0.0,     # minutes (accumulated wear proxy)
        failure_prob: float = 0.0,     # from AI4I model  [0, 1]
    ) -> dict:
        """
        Estimate RUL from vehicle parameters.

        Parameters map to degradation level [0=fresh, 1=end-of-life]:
        - tool_wear    → primary wear signal
        - failure_prob → AI4I model's assessment
        - temperature  → thermal stress contribution
        - torque       → mechanical stress contribution
        - rpm          → speed stress contribution

        Returns
        -------
        dict with remaining_life_cycles, remaining_life_pct, rul_category, interpretation
        """
        # Compute a normalised degradation level [0, 1] from vehicle params
        wear_level   = float(np.clip(tool_wear   / 250.0, 0, 1))
        temp_level   = float(np.clip((temperature - 290) / 110.0, 0, 1))  # 290–400 K range
        torque_level = float(np.clip(torque       / 350.0, 0, 1))
        rpm_level    = float(np.clip((rpm - 600)  / 5400.0, 0, 1))
        fp_level     = float(np.clip(failure_prob, 0, 1))

        # Weighted composite degradation — wear + failure_prob dominate
        deg = (0.35 * wear_level
               + 0.30 * fp_level
               + 0.15 * temp_level
               + 0.12 * torque_level
               + 0.08 * rpm_level)
        deg = float(np.clip(deg, 0, 1))

        sensor_vec = self._build_sensor_vector(deg)
        raw_rul    = float(self._model.predict([sensor_vec])[0])
        rul        = float(np.clip(raw_rul, 0, _MAX_RUL))

        category = self._rul_category(rul)
        pct      = round(rul / _MAX_RUL * 100, 1)

        return {
            'remaining_life_cycles': int(round(rul)),
            'remaining_life_pct':    pct,
            'rul_category':          category,
            'degradation_level':     round(deg, 4),
            'interpretation':        self._interpret(rul, category),
        }

    def predict_from_sensors(self, sensor_values: list[float]) -> dict:
        """Predict from a raw feature vector (same format as training)."""
        if len(sensor_values) != len(self._features):
            raise ValueError(
                f'Expected {len(self._features)} features, got {len(sensor_values)}'
            )
        raw_rul  = float(self._model.predict([sensor_values])[0])
        rul      = float(np.clip(raw_rul, 0, _MAX_RUL))
        category = self._rul_category(rul)
        return {
            'remaining_life_cycles': int(round(rul)),
            'remaining_life_pct':    round(rul / _MAX_RUL * 100, 1),
            'rul_category':          category,
            'degradation_level':     None,
            'interpretation':        self._interpret(rul, category),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_sensor_vector(self, deg: float) -> list[float]:
        """
        Map degradation level [0, 1] to a C-MAPSS FD001 sensor vector.

        For sensors that increase with degradation:  value = min + deg*(max-min)
        For sensors that decrease with degradation:  value = max - deg*(max-min)
        Op settings are held at typical values (near-zero for op1/op2; 100 for op3).
        """
        # Degradation direction per sensor  (+1 = rises, -1 = drops)
        direction = {
            's2':+1, 's3':+1, 's4':+1, 's7':-1, 's8':+1, 's9':+1,
            's11':+1,'s12':-1,'s13':+1,'s14':-1,'s15':+1,'s17':+1,
            's20':-1,'s21':-1,
        }

        base = []
        for s in self._sensors:
            lo, hi = _SENSOR_RANGES[s]
            d = direction.get(s, +1)
            if d == +1:
                val = lo + deg * (hi - lo)
            else:
                val = hi - deg * (hi - lo)
            base.append(val)

        # op settings: op1≈0, op2≈0, op3=100
        ops = [0.0, 0.0, 100.0]

        # Rolling means = same values (single-point prediction)
        rolling = list(base)

        return ops + base + rolling

    @staticmethod
    def _rul_category(rul: float) -> str:
        for threshold, label in _RISK_BANDS:
            if rul > threshold:
                return label
        return 'Critical'

    @staticmethod
    def _interpret(rul: float, category: str) -> str:
        cycles = int(round(rul))
        if category == 'Healthy':
            return (f'Component is in good health with approximately {cycles} operating '
                    f'cycles remaining. No immediate maintenance required.')
        if category == 'Fair':
            return (f'Component shows mild wear with ~{cycles} cycles remaining. '
                    f'Plan maintenance within the next service window.')
        if category == 'Degraded':
            return (f'Component is degraded — only ~{cycles} cycles estimated remaining. '
                    f'Schedule maintenance within the next few days.')
        return (f'Component is critically worn with ~{cycles} cycles remaining. '
                f'Immediate maintenance required to prevent failure.')
