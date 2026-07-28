"""
Failure Probability Predictor  –  AI4I 2020 Predictive Maintenance Dataset
===========================================================================
Uses an ensemble of XGBoost + Random Forest classifiers trained on the AI4I
2020 dataset to estimate the probability of machine / component failure given
live sensor readings.

Input features (must be supplied by the caller):
    air_temp    – Air temperature (K)
    proc_temp   – Process temperature (K)
    rpm         – Rotational speed (rpm)
    torque      – Torque (Nm)
    tool_wear   – Tool wear (minutes)
"""

from __future__ import annotations
import os
import numpy as np
import joblib

_MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')

# Thresholds for failure risk labels
_RISK_BANDS = [
    (0.75, 'Critical'),
    (0.50, 'High'),
    (0.25, 'Medium'),
    (0.00, 'Low'),
]


class FailureProbabilityPredictor:
    """
    Ensemble (XGBoost + RF) failure-probability predictor.

    The final probability is the average of the two models' positive-class
    probability to smooth out individual model biases.
    """

    def __init__(self):
        self._xgb     = joblib.load(os.path.join(_MODEL_DIR, 'ai4i_xgb.pkl'))
        self._rf      = joblib.load(os.path.join(_MODEL_DIR, 'ai4i_rf.pkl'))
        self._features = joblib.load(os.path.join(_MODEL_DIR, 'ai4i_features.pkl'))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        air_temp:  float = 298.0,
        proc_temp: float = 308.0,
        rpm:       float = 1500.0,
        torque:    float = 40.0,
        tool_wear: float = 0.0,
    ) -> dict:
        """
        Estimate failure probability from sensor readings.

        Parameters
        ----------
        air_temp   : Ambient air temperature in Kelvin (default 298 K ≈ 25 °C)
        proc_temp  : Process temperature in Kelvin
        rpm        : Rotational speed in revolutions per minute
        torque     : Torque in Newton-metres
        tool_wear  : Accumulated tool wear in minutes

        Returns
        -------
        dict:
            failure_probability – float [0, 1]
            failure_risk        – str  (Low / Medium / High / Critical)
            contributing_factors – list[str]  (sensor readings that cross thresholds)
        """
        import pandas as pd
        X = pd.DataFrame(
            [[air_temp, proc_temp, rpm, torque, tool_wear]],
            columns=self._features,
        )

        prob_xgb = self._xgb.predict_proba(X)[0][1]
        prob_rf  = self._rf.predict_proba(X)[0][1]
        prob     = float((prob_xgb + prob_rf) / 2)

        risk = self._risk_label(prob)
        factors = self._contributing_factors(air_temp, proc_temp, rpm, torque, tool_wear)

        return {
            'failure_probability':    round(prob, 4),
            'failure_risk':           risk,
            'contributing_factors':   factors,
            'model_probabilities': {
                'xgboost': round(float(prob_xgb), 4),
                'random_forest': round(float(prob_rf), 4),
            },
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _risk_label(prob: float) -> str:
        for threshold, label in _RISK_BANDS:
            if prob >= threshold:
                return label
        return 'Low'

    @staticmethod
    def _contributing_factors(air_temp, proc_temp, rpm, torque, tool_wear) -> list[str]:
        """Flag readings that exceed typical safe operating ranges."""
        factors = []
        temp_diff = proc_temp - air_temp
        if temp_diff > 12:
            factors.append(f'High temperature differential ({temp_diff:.1f} K above ambient)')
        if rpm < 1200 or rpm > 2800:
            factors.append(f'Abnormal rotational speed ({rpm:.0f} rpm)')
        if torque > 65:
            factors.append(f'High torque loading ({torque:.1f} Nm)')
        if tool_wear > 180:
            factors.append(f'Excessive tool wear ({tool_wear:.0f} min)')
        if not factors:
            factors.append('All sensor readings within normal operating range')
        return factors
