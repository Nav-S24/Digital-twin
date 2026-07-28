"""
Recommendation Engine
=====================
Aggregates outputs from all sub-models and OBD knowledge-base to produce:
  - maintenance_urgency  (Immediate / Soon / Monitor / None)
  - trip_status          (STOP / CAUTION / OK)
  - driver_advice        (plain-English sentence for the driver)
  - maintenance_actions  (ordered list of specific action items)
  - estimated_repair_window (human time-string)
"""

from __future__ import annotations
from .obd_knowledge_base import SEVERITY_RANK


# ── Trip status rules ──────────────────────────────────────────────────────
def _trip_status(overall_severity: str, failure_prob: float, rul_pct: float,
                 component_risk: str) -> str:
    if overall_severity == 'Critical' or failure_prob >= 0.75 or rul_pct < 10:
        return 'STOP'
    if (overall_severity == 'High' or failure_prob >= 0.45 or rul_pct < 30
            or component_risk in ('High', 'Critical')):
        return 'CAUTION'
    return 'OK'


def _urgency(trip: str, overall_severity: str) -> str:
    if trip == 'STOP':
        return 'Immediate'
    if trip == 'CAUTION' or overall_severity in ('High', 'Critical'):
        return 'Soon'
    if overall_severity == 'Medium':
        return 'Monitor'
    return 'None'


def _repair_window(urgency: str) -> str:
    return {
        'Immediate': 'Do not drive – arrange tow or emergency service now',
        'Soon':      'Within 24–48 hours',
        'Monitor':   'Within 1–2 weeks',
        'None':      'Next scheduled service',
    }.get(urgency, 'Next scheduled service')


def _driver_advice(trip: str, urgency: str, severity: str, component_risk: str) -> str:
    if trip == 'STOP':
        return ('⛔ Pull over safely and switch off the engine. '
                'Do not continue driving. Contact roadside assistance immediately.')
    if trip == 'CAUTION':
        return ('⚠️  Vehicle can be driven for short distances with caution. '
                'Avoid high speed or heavy load. '
                'Arrange repair at the earliest opportunity.')
    if urgency == 'Monitor':
        return ('✅ Vehicle is safe to drive. '
                'Monitor the indicated system and book a service appointment within 1–2 weeks.')
    return ('✅ No immediate action required. '
            'Address at your next routine service interval.')


def _maintenance_actions(obd_explanations: list[dict], failure_prob: float,
                         rul_pct: float, affected_components: list[str]) -> list[str]:
    actions = []

    # From OBD codes
    seen = set()
    for exp in obd_explanations:
        sev = exp.get('severity', 'Low')
        rec = exp.get('recommendation', '')
        code = exp.get('code', '')
        if rec and rec not in seen:
            actions.append(f"[{code} – {sev}] {rec}")
            seen.add(rec)

    # From predictive models
    if failure_prob >= 0.75:
        actions.append('[AI4I Model] Emergency inspection required – failure imminent')
    elif failure_prob >= 0.45:
        actions.append('[AI4I Model] Schedule component inspection within 48 hours')
    elif failure_prob >= 0.25:
        actions.append('[AI4I Model] Book routine health check within 2 weeks')

    if rul_pct < 15:
        actions.append('[RUL Model] Component approaching end-of-life – replacement required')
    elif rul_pct < 40:
        actions.append('[RUL Model] Component wear detected – monitor and plan replacement')

    for comp in affected_components:
        if comp and 'no specific' not in comp.lower():
            actions.append(f'[Component] Inspect / service: {comp}')

    return actions if actions else ['No specific actions required at this time']


# ── NHTSA Safety Recall lookup ─────────────────────────────────────────────
def _recall_hint(make: str | None, model: str | None, year: int | None) -> str | None:
    """Optional: construct NHTSA recall URL for the vehicle if details are known."""
    if not (make and model and year):
        return None
    make_enc  = make.upper().replace(' ', '%20')
    model_enc = model.upper().replace(' ', '%20')
    return (f'https://api.nhtsa.gov/recalls/recallsByVehicle'
            f'?make={make_enc}&model={model_enc}&modelYear={year}')


# ── Main function ──────────────────────────────────────────────────────────

def build_recommendation(
    obd_explanations:     list[dict],
    failure_result:       dict,
    rul_result:           dict,
    component_result:     dict,
    overall_severity:     str,
    vehicle_make:         str | None = None,
    vehicle_model:        str | None = None,
    vehicle_year:         int | None = None,
) -> dict:
    """
    Combine all model outputs into a unified recommendation payload.

    Parameters
    ----------
    obd_explanations : list of dicts from FaultExplanationEngine.explain_many()
    failure_result   : dict from FailureProbabilityPredictor.predict()
    rul_result       : dict from RULPredictor.predict_from_vehicle()
    component_result : dict from ComponentFailureAssessor.assess_from_vehicle()
    overall_severity : str – worst OBD severity across all codes
    vehicle_* :        optional vehicle details for NHTSA recall lookup

    Returns
    -------
    dict – full recommendation payload
    """
    failure_prob    = failure_result.get('failure_probability', 0.0)
    rul_pct         = rul_result.get('remaining_life_pct', 100.0)
    component_risk  = component_result.get('failure_risk', 'Low')
    affected_comps  = component_result.get('affected_components', [])

    trip    = _trip_status(overall_severity, failure_prob, rul_pct, component_risk)
    urgency = _urgency(trip, overall_severity)
    advice  = _driver_advice(trip, urgency, overall_severity, component_risk)
    window  = _repair_window(urgency)
    actions = _maintenance_actions(obd_explanations, failure_prob, rul_pct, affected_comps)
    recall  = _recall_hint(vehicle_make, vehicle_model, vehicle_year)

    return {
        'maintenance_urgency':      urgency,
        'trip_status':              trip,
        'driver_advice':            advice,
        'estimated_repair_window':  window,
        'maintenance_actions':      actions,
        'nhtsa_recall_check_url':   recall,
    }
