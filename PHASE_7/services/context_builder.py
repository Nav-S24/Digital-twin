"""
Phase 7 - ContextBuilder

Builds the MINIMAL grounded context object handed to the LLM for a given
intent. Never touches full CSVs or unrelated columns. Also tracks which
data sources were actually used, for the response's `data_sources` field.
"""

from typing import Optional
from services.vehicle_service import VehicleService, VehicleNotFoundError
from services.diagnostic_service import DiagnosticService
from services.intent_detector import Intent

SOURCE_MERGED = "Merged Vehicle Intelligence"
SOURCE_PHASE5 = "Phase 5 Diagnostic Store"
SOURCE_KB = "OBD Knowledge Base"
SOURCE_RAW_OBD = "OBD Fallback Reference"
SOURCE_GENERAL = "General Automotive Knowledge (not vehicle-specific)"


class ContextBuilder:

    @staticmethod
    def build(intent: Intent, vehicle_id: Optional[str], obd_codes: list[str]) -> dict:
        """
        Returns:
            {
                "intent": ...,
                "vehicle_context": {...} or None,
                "diagnostic_context": [...] or [],
                "vehicle_error": str or None,
                "data_sources": [...]
            }
        """
        result = {
            "intent": intent.value,
            "vehicle_context": None,
            "diagnostic_context": [],
            "vehicle_error": None,
            "data_sources": [],
        }

        vehicle_intents = {
            Intent.HEALTH_EXPLANATION,
            Intent.VEHICLE_STATUS,
            Intent.FAILURE_RISK,
            Intent.RUL_QUERY,
            Intent.MAINTENANCE_QUERY,
        }

        # ---- Vehicle-scoped intents ----
        if intent in vehicle_intents:
            if not vehicle_id:
                result["vehicle_error"] = "No vehicle selected - cannot answer a vehicle-specific question."
            else:
                try:
                    if intent == Intent.HEALTH_EXPLANATION:
                        result["vehicle_context"] = VehicleService.health_view(vehicle_id)
                    elif intent == Intent.VEHICLE_STATUS:
                        result["vehicle_context"] = VehicleService.status_view(vehicle_id)
                    elif intent == Intent.FAILURE_RISK:
                        result["vehicle_context"] = VehicleService.failure_risk_view(vehicle_id)
                    elif intent == Intent.RUL_QUERY:
                        result["vehicle_context"] = VehicleService.rul_view(vehicle_id)
                    elif intent == Intent.MAINTENANCE_QUERY:
                        result["vehicle_context"] = VehicleService.maintenance_view(vehicle_id)
                    result["data_sources"].append(SOURCE_MERGED)
                except VehicleNotFoundError:
                    result["vehicle_error"] = f"Vehicle_ID '{vehicle_id}' was not found in the vehicle store."

            # MAINTENANCE_QUERY may additionally pull Phase 5 if the user gave a code
            if intent == Intent.MAINTENANCE_QUERY and obd_codes:
                diag = DiagnosticService.lookup_many(obd_codes)
                result["diagnostic_context"] = diag
                for d in diag:
                    if d["source"] != "NOT_FOUND" and d["source"] not in result["data_sources"]:
                        result["data_sources"].append(d["source"])

        # ---- Fault diagnosis: Phase5 -> KB -> raw fallback ----
        elif intent == Intent.FAULT_DIAGNOSIS:
            if not obd_codes:
                result["vehicle_error"] = "No OBD code was found in the message to diagnose."
            else:
                diag = DiagnosticService.lookup_many(obd_codes)
                result["diagnostic_context"] = diag
                for d in diag:
                    if d["source"] != "NOT_FOUND" and d["source"] not in result["data_sources"]:
                        result["data_sources"].append(d["source"])

        # ---- Driving safety: vehicle data and/or OBD diagnostic data ----
        elif intent == Intent.DRIVING_SAFETY:
            if obd_codes:
                diag = DiagnosticService.lookup_many(obd_codes)
                result["diagnostic_context"] = diag
                for d in diag:
                    if d["source"] != "NOT_FOUND" and d["source"] not in result["data_sources"]:
                        result["data_sources"].append(d["source"])
            if vehicle_id:
                try:
                    result["vehicle_context"] = VehicleService.status_view(vehicle_id)
                    if SOURCE_MERGED not in result["data_sources"]:
                        result["data_sources"].append(SOURCE_MERGED)
                except VehicleNotFoundError:
                    if not obd_codes:
                        result["vehicle_error"] = f"Vehicle_ID '{vehicle_id}' was not found in the vehicle store."
            if not vehicle_id and not obd_codes:
                result["vehicle_error"] = "No vehicle selected and no OBD code provided."

        # ---- General knowledge: no retrieval, clearly labeled ----
        elif intent == Intent.VEHICLE_KNOWLEDGE:
            result["data_sources"].append(SOURCE_GENERAL)

        return result
