"""
Fault Explanation Engine
========================
Converts raw OBD fault codes into human-readable, structured explanations
suitable for both technical and driver-friendly consumption.
"""

from __future__ import annotations
from typing import Any
from .obd_knowledge_base import OBDKnowledgeBase


# Friendly descriptions for each affected system (for driver display)
_SYSTEM_HINTS: dict[str, str] = {
    'Fuel & Emission':           "your engine's fuel and emissions control systems",
    'Ignition System':           'the ignition system (spark plugs / timing)',
    'Transmission':              'the automatic or manual transmission',
    'Vehicle Speed & Control':   'vehicle speed, idle, or traction-control systems',
    'Cooling System':            'the engine cooling system',
    'Electrical/Charging':       "the vehicle's electrical and charging system",
    'Sensor/Circuit':            'an onboard sensor or wiring circuit',
    'Body':                      'a body-control module or interior system',
    'Chassis':                   'a chassis system (ABS / steering / suspension)',
    'Network/Communication':     'the onboard communication network (CAN bus)',
    'Powertrain':                'general powertrain components',
    'Unknown':                   'an unclassified vehicle system',
}

# Plain-English severity summaries shown to the driver
_SEVERITY_LABELS: dict[str, str] = {
    'Critical': '🔴 Critical – Stop driving now and call for assistance',
    'High':     '🟠 High – Seek repair within 24–48 hours',
    'Medium':   '🟡 Medium – Schedule service within 1–2 weeks',
    'Low':      '🟢 Low – Monitor and address at next routine service',
    'Unknown':  '⚪ Unknown – Consult a mechanic for diagnosis',
}


class FaultExplanationEngine:
    """
    Provides structured and driver-friendly fault explanations.

    Usage
    -----
    >>> engine = FaultExplanationEngine()
    >>> result = engine.explain("P0420")
    >>> print(result["driver_friendly"])
    """

    def __init__(self):
        self._kb = OBDKnowledgeBase.get()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def explain(self, code: str) -> dict[str, Any]:
        """
        Return full structured explanation for a single DTC code.

        Returns
        -------
        dict with keys:
            code, description, severity, severity_label,
            affected_system, system_hint, symptoms, impact,
            recommendation, driver_friendly
        """
        entry = self._kb.lookup(code)
        return self._build_explanation(entry)

    def explain_many(self, codes: list[str]) -> list[dict[str, Any]]:
        """Explain multiple DTC codes and return list of explanations."""
        return [self.explain(c) for c in codes]

    def summarise(self, codes: list[str]) -> dict[str, Any]:
        """
        Return a concise summary across multiple codes.

        Includes:
        - overall_severity (worst across all codes)
        - unique systems affected
        - aggregated symptom list (deduplicated)
        - highest-priority recommendation
        """
        explanations = self.explain_many(codes)
        if not explanations:
            return {}

        from .obd_knowledge_base import SEVERITY_RANK
        explanations.sort(key=lambda e: SEVERITY_RANK.get(e['severity'], 0), reverse=True)
        worst = explanations[0]

        all_symptoms: list[str] = []
        all_systems: set[str] = set()
        for e in explanations:
            all_symptoms.extend(e.get('symptoms', []))
            all_systems.add(e.get('affected_system', 'Unknown'))

        return {
            'overall_severity':      worst['severity'],
            'severity_label':        worst['severity_label'],
            'systems_affected':      sorted(all_systems),
            'aggregated_symptoms':   list(dict.fromkeys(all_symptoms)),   # preserves order, deduplicates
            'primary_recommendation': worst['recommendation'],
            'all_codes':             [e['code'] for e in explanations],
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_explanation(self, entry: dict) -> dict[str, Any]:
        code        = entry.get('code', 'UNKNOWN')
        description = entry.get('description', 'No description available')
        severity    = entry.get('severity', 'Unknown')
        system      = entry.get('affected_system', 'Unknown')
        symptoms    = entry.get('symptoms', [])
        impact      = entry.get('impact', 'Impact unknown')
        rec         = entry.get('recommendation', 'Consult a mechanic')

        driver_friendly = self._make_driver_friendly(
            code, description, severity, system, symptoms, rec
        )

        return {
            'code':            code,
            'description':     description,
            'severity':        severity,
            'severity_label':  _SEVERITY_LABELS.get(severity, '⚪ Unknown'),
            'affected_system': system,
            'system_hint':     _SYSTEM_HINTS.get(system, 'an onboard vehicle system'),
            'symptoms':        symptoms,
            'impact':          impact,
            'recommendation':  rec,
            'driver_friendly': driver_friendly,
        }

    @staticmethod
    def _make_driver_friendly(code, description, severity, system, symptoms, rec) -> str:
        sym_str = ', '.join(symptoms[:3]) if symptoms else 'no specific symptoms listed'
        label   = _SEVERITY_LABELS.get(severity, '⚪ Unknown')
        hint    = _SYSTEM_HINTS.get(system, 'an onboard vehicle system')
        return (
            f"Your vehicle's diagnostic system detected code {code}. "
            f"This relates to {hint} ({description}). "
            f"You may notice: {sym_str}. "
            f"Severity: {label}. "
            f"Recommended action: {rec}."
        )
