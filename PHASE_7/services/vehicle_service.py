"""
Phase 7 - VehicleService

Looks up a vehicle by Vehicle_ID from the merged_vehicle_state index and
exposes narrow, purpose-built views of the data so ContextBuilder never
has to hand the LLM more fields than a given intent needs.
"""

from typing import Optional
from data.loaders import get_vehicle


class VehicleNotFoundError(Exception):
    def __init__(self, vehicle_id: str):
        self.vehicle_id = vehicle_id
        super().__init__(f"Vehicle_ID '{vehicle_id}' not found in vehicle store")


class VehicleService:

    @staticmethod
    def lookup(vehicle_id: str) -> dict:
        """Raw row lookup. Raises VehicleNotFoundError if missing."""
        vehicle = get_vehicle(vehicle_id)
        if vehicle is None:
            raise VehicleNotFoundError(vehicle_id)
        return vehicle

    @staticmethod
    def exists(vehicle_id: str) -> bool:
        return get_vehicle(vehicle_id) is not None

    # ---- Narrow, intent-scoped views ----

    @staticmethod
    def health_view(vehicle_id: str) -> dict:
        v = VehicleService.lookup(vehicle_id)
        return {
            "Vehicle_ID": v["Vehicle_ID"],
            "engine_health": v["engine_health"],
            "battery_health": v["battery_health"],
            "vehicle_health": v["vehicle_health"],
            "health_class": v["health_class"],
            "ml_health_score": v["ml_health_score"],
            "Top_Risk_Sensor": v["Top_Risk_Sensor"],
            "Top_Risk_SHAP_Value": v["Top_Risk_SHAP_Value"],
            "Affected_System": v["Affected_System"],
            "Reason": v["Reason"],
        }

    @staticmethod
    def status_view(vehicle_id: str) -> dict:
        v = VehicleService.lookup(vehicle_id)
        return {
            "Vehicle_ID": v["Vehicle_ID"],
            "vehicle_health": v["vehicle_health"],
            "health_class": v["health_class"],
            "trip_readiness": v["trip_readiness"],
            "fault_count": v["fault_count"],
            "Urgency": v["Urgency"],
        }

    @staticmethod
    def failure_risk_view(vehicle_id: str) -> dict:
        v = VehicleService.lookup(vehicle_id)
        return {
            "Vehicle_ID": v["Vehicle_ID"],
            "Failure_Probability": v["Failure_Probability"],
            "Failure_Risk_Percentage": v["Failure_Risk_Percentage"],
            "Urgency": v["Urgency"],
            "Top_Risk_Sensor": v["Top_Risk_Sensor"],
            "Top_Risk_SHAP_Value": v["Top_Risk_SHAP_Value"],
            "Affected_System": v["Affected_System"],
            "Reason": v["Reason"],
        }

    @staticmethod
    def rul_view(vehicle_id: str) -> dict:
        v = VehicleService.lookup(vehicle_id)
        return {
            "Vehicle_ID": v["Vehicle_ID"],
            "Remaining_Useful_Life_Cycles": v["Remaining_Useful_Life_Cycles"],
            "Remaining_Useful_Life_KM": v["Remaining_Useful_Life_KM"],
            "Urgency": v["Urgency"],
            "Book_Service_Within_Days": v["Book_Service_Within_Days"],
        }

    @staticmethod
    def maintenance_view(vehicle_id: str) -> dict:
        v = VehicleService.lookup(vehicle_id)
        return {
            "Vehicle_ID": v["Vehicle_ID"],
            "Recommended_Action": v["Recommended_Action"],
            "Maintenance_Priority": v["Maintenance_Priority"],
            "Book_Service_Within_Days": v["Book_Service_Within_Days"],
            "Affected_System": v["Affected_System"],
            "Reason": v["Reason"],
        }
