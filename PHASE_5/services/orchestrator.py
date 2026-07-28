"""
Diagnostic Orchestrator
=======================
Single entry-point that wires together:
  1. OBD Knowledge Base  →  FaultExplanationEngine
  2. AI4I  →  FailureProbabilityPredictor
  3. NASA C-MAPSS  →  RULPredictor
  4. Scania APS  →  ComponentFailureAssessor
  5. RecommendationEngine

Call  DiagnosticOrchestrator().diagnose(...)  from the FastAPI route handler.
"""

from __future__ import annotations
from typing import Optional

from .fault_explanation   import FaultExplanationEngine
from .failure_probability import FailureProbabilityPredictor
from .rul_predictor       import RULPredictor
from .component_failure   import ComponentFailureAssessor
from .recommendation_engine import build_recommendation
from .obd_knowledge_base  import OBDKnowledgeBase


class DiagnosticOrchestrator:
    """Thread-safe singleton; services are loaded once at startup."""

    _instance: Optional['DiagnosticOrchestrator'] = None

    def __new__(cls):
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._explanation_engine = FaultExplanationEngine()
            obj._failure_predictor  = FailureProbabilityPredictor()
            obj._rul_predictor      = RULPredictor()
            obj._component_assessor = ComponentFailureAssessor()
            obj._kb                 = OBDKnowledgeBase.get()
            cls._instance = obj
        return cls._instance

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def diagnose(
        self,
        fault_codes:    list[str],
        temperature:    float = 298.0,    # K  (ambient / air temp)
        rpm:            float = 1500.0,
        torque:         float = 40.0,
        tool_wear:      float = 0.0,
        process_temp:   float | None = None,   # K, defaults to temp + 10
        vehicle_make:   str | None = None,
        vehicle_model:  str | None = None,
        vehicle_year:   int | None = None,
    ) -> dict:
        """
        Full Phase-5 diagnostic pipeline.

        Parameters
        ----------
        fault_codes  : list of OBD DTC strings  e.g. ['P0420', 'P0300']
        temperature  : ambient air temperature in Kelvin
        rpm          : engine revolutions per minute
        torque       : engine torque in Nm
        tool_wear    : accumulated wear proxy in minutes
        process_temp : process / coolant temperature (defaults to temperature + 10 K)
        vehicle_*    : optional vehicle identification for NHTSA recall lookup

        Returns
        -------
        dict – complete diagnostic JSON
        """
        if process_temp is None:
            process_temp = temperature + 10.0

        # 1. OBD fault explanation
        explanations     = self._explanation_engine.explain_many(fault_codes)
        obd_summary      = self._explanation_engine.summarise(fault_codes)
        overall_severity = self._kb.max_severity(fault_codes) if fault_codes else 'Unknown'

        # 2. AI4I failure probability
        failure_result = self._failure_predictor.predict(
            air_temp   = temperature,
            proc_temp  = process_temp,
            rpm        = rpm,
            torque     = torque,
            tool_wear  = tool_wear,
        )
        failure_prob = failure_result['failure_probability']

        # 3. NASA RUL
        rul_result = self._rul_predictor.predict_from_vehicle(
            rpm          = rpm,
            temperature  = process_temp,
            torque       = torque,
            tool_wear    = tool_wear,
            failure_prob = failure_prob,
        )
        rul_pct = rul_result['remaining_life_pct']

        # 4. Scania component risk
        component_result = self._component_assessor.assess_from_vehicle(
            rpm          = rpm,
            temperature  = process_temp,
            torque       = torque,
            tool_wear    = tool_wear,
            failure_prob = failure_prob,
            rul_pct      = rul_pct,
        )

        # 5. Recommendation engine
        recommendation = build_recommendation(
            obd_explanations = explanations,
            failure_result   = failure_result,
            rul_result       = rul_result,
            component_result = component_result,
            overall_severity = overall_severity,
            vehicle_make     = vehicle_make,
            vehicle_model    = vehicle_model,
            vehicle_year     = vehicle_year,
        )

        # ── Assemble final payload ──────────────────────────────────────
        # Primary summary (mirrors the spec's example output)
        primary = explanations[0] if explanations else {}

        return {
            # ── Fault-code summary ──
            'fault_codes':         fault_codes,
            'code':                primary.get('code', ''),
            'description':         primary.get('description', 'No codes supplied'),
            'severity':            overall_severity,
            'affected_system':     primary.get('affected_system', 'Unknown'),

            # ── Predictive model outputs ──
            'failure_probability': failure_result['failure_probability'],
            'failure_risk':        failure_result['failure_risk'],
            'remaining_life':      rul_result['remaining_life_cycles'],
            'remaining_life_pct':  rul_result['remaining_life_pct'],
            'rul_category':        rul_result['rul_category'],
            'component_risk':      component_result['failure_risk'],
            'affected_components': component_result['affected_components'],

            # ── Recommendations ──
            'recommendation':          recommendation['maintenance_actions'][0]
                                        if recommendation['maintenance_actions'] else '',
            'maintenance_urgency':     recommendation['maintenance_urgency'],
            'trip_status':             recommendation['trip_status'],
            'driver_advice':           recommendation['driver_advice'],
            'estimated_repair_window': recommendation['estimated_repair_window'],
            'maintenance_actions':     recommendation['maintenance_actions'],
            'nhtsa_recall_check_url':  recommendation.get('nhtsa_recall_check_url'),

            # ── Detailed breakdowns ──
            'obd_details':       explanations,
            'obd_summary':       obd_summary,
            'model_details': {
                'failure_model':   failure_result,
                'rul_model':       rul_result,
                'component_model': component_result,
            },
        }
