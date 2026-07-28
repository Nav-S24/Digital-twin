"""
Component Failure Assessment  –  Scania APS Failure Dataset
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd
import joblib

_MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')

_RISK_BANDS = [
    (0.70, 'Critical'),
    (0.45, 'High'),
    (0.20, 'Medium'),
    (0.00, 'Low'),
]


class ComponentFailureAssessor:
    _rf = None
    _imputer = None
    _features = None

    def _load_models(self):
        if self._rf is None:
            ComponentFailureAssessor._rf       = joblib.load(os.path.join(_MODEL_DIR, 'scania_rf.pkl'))
            ComponentFailureAssessor._imputer  = joblib.load(os.path.join(_MODEL_DIR, 'scania_imputer.pkl'))
            ComponentFailureAssessor._features = joblib.load(os.path.join(_MODEL_DIR, 'scania_features.pkl'))

    def assess_from_vehicle(self, rpm=1500.0, temperature=310.0, torque=40.0,
                             tool_wear=0.0, failure_prob=0.0, rul_pct=100.0) -> dict:
        sensor_score = self._sensor_risk_score(rpm, temperature, torque, tool_wear)
        rul_score    = float(1.0 - rul_pct / 100.0)
        fp_score     = float(failure_prob)
        composite    = float(np.clip(0.45*fp_score + 0.35*rul_score + 0.20*sensor_score, 0, 1))
        risk         = self._risk_label(composite)
        return {
            'failure_risk':        risk,
            'risk_score':          round(composite, 4),
            'risk_factors':        self._risk_factors(rpm, temperature, torque, tool_wear, fp_score, rul_pct),
            'affected_components': self._likely_components(risk, temperature, torque, tool_wear),
            'score_breakdown': {
                'failure_probability_weight': round(0.45*fp_score, 4),
                'rul_weight':                 round(0.35*rul_score, 4),
                'sensor_anomaly_weight':      round(0.20*sensor_score, 4),
            },
        }

    def assess_from_aps_sensors(self, sensor_dict: dict) -> dict:
        self._load_models()
        row  = pd.DataFrame([sensor_dict]).reindex(columns=self._features)
        X_df = pd.DataFrame(self._imputer.transform(row), columns=self._features)
        prob = float(self._rf.predict_proba(X_df)[0][1])
        risk = self._risk_label(prob)
        return {
            'failure_risk':        risk,
            'risk_score':          round(prob, 4),
            'risk_factors':        [f'APS sensor model probability: {prob:.1%}'],
            'affected_components': self._likely_components(risk),
        }

    @staticmethod
    def _sensor_risk_score(rpm, temperature, torque, tool_wear) -> float:
        score = 0.0
        if rpm < 800 or rpm > 3500:  score += 0.30
        if temperature > 370:        score += 0.35
        elif temperature > 355:      score += 0.15
        if torque > 80:              score += 0.20
        if tool_wear > 200:          score += 0.25
        elif tool_wear > 150:        score += 0.10
        return min(score, 1.0)

    @staticmethod
    def _risk_label(score: float) -> str:
        for threshold, label in _RISK_BANDS:
            if score >= threshold:
                return label
        return 'Low'

    @staticmethod
    def _risk_factors(rpm, temperature, torque, tool_wear, fp, rul_pct) -> list:
        factors = []
        if fp > 0.5:           factors.append(f'High machine-failure probability ({fp:.0%})')
        if rul_pct < 30:       factors.append(f'Low remaining useful life ({rul_pct:.0f}%)')
        if temperature > 360:  factors.append(f'Elevated operating temperature ({temperature:.0f} K)')
        if torque > 75:        factors.append(f'High torque load ({torque:.0f} Nm)')
        if tool_wear > 170:    factors.append(f'Advanced tool wear ({tool_wear:.0f} min)')
        if rpm < 900 or rpm > 3200: factors.append(f'Abnormal engine speed ({rpm:.0f} rpm)')
        if not factors:        factors.append('All monitored parameters within acceptable ranges')
        return factors

    @staticmethod
    def _likely_components(risk, temperature=310, torque=40, tool_wear=0) -> list:
        comps = []
        if risk in ('Critical', 'High'): comps += ['Air Pressure Compressor', 'Pressure Relief Valve']
        if temperature > 355:            comps.append('Cooling System / Radiator')
        if torque > 75:                  comps.append('Drive Shaft / Gearbox')
        if tool_wear > 150:              comps += ['Brake Pads', 'Engine Bearings']
        if risk == 'Critical':           comps.append('APS Sensor Array')
        if not comps:                    comps.append('No specific components flagged at current risk level')
        return comps
