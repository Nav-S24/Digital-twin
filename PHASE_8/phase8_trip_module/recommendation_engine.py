"""
recommendation_engine.py
Phase 8 - Trip Intelligence Module

Recommendation Engine
----------------------
Produces a prioritized list of actionable, human-readable recommendations
based on vehicle health, digital twin status, weather, fuel state, and
(NEW) driver behaviour + critical-component service centre escalation.
Pure rule-based (no ML) so it is fully transparent and auditable.

CHANGE LOG (this revision):
  - Each recommendation is now tagged with a priority: Critical / High /
    Medium / Low, and the list is sorted by priority (Critical first).
  - `generate()` keeps its ORIGINAL signature and return type (List[str])
    for full backward compatibility with existing callers — it now simply
    returns the same strings sorted by priority instead of insertion order.
  - NEW `generate_detailed()` returns the same recommendations as a list of
    {"priority": ..., "text": ...} dicts, used by trip_engine.py to populate
    TripResponse.recommendations_detailed for the dashboard's grouped view.
  - NEW: a Driver Behaviour Score input now contributes recommendations
    (harsh braking / aggressive acceleration / overspeeding guidance).
  - NEW: a "Visit nearest service centre immediately" Critical recommendation
    is added whenever a component is critically unhealthy — this mirrors
    (and is consistent with) the standalone Service Centre Recommendation
    panel powered by service_centre_engine.py.
"""

from __future__ import annotations

from typing import List, Tuple

from api.schemas import FuelEstimate, RouteInfo, VehicleState, WeatherInfo
from config import risk_thresholds, settings

_PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


class RecommendationEngine:
    def __init__(self, thresholds=risk_thresholds):
        self.t = thresholds

    # ------------------------------------------------------------------ #
    # Public API — UNCHANGED signature/return type (List[str])
    # ------------------------------------------------------------------ #
    def generate(
        self,
        vehicle: VehicleState,
        weather: WeatherInfo,
        fuel: FuelEstimate,
        route: RouteInfo,
    ) -> List[str]:
        return [item["text"] for item in self.generate_detailed(vehicle, weather, fuel, route)]

    # ------------------------------------------------------------------ #
    # NEW: detailed, priority-tagged recommendations
    # ------------------------------------------------------------------ #
    def generate_detailed(
        self,
        vehicle: VehicleState,
        weather: WeatherInfo,
        fuel: FuelEstimate,
        route: RouteInfo,
    ) -> List[dict]:
        recs: List[Tuple[str, str]] = []  # (priority, text)

        # --- Critical component escalation -> Service Centre visit ---
        critical_component = self._has_critical_component_issue(vehicle)
        if critical_component:
            recs.append(("Critical", "Visit the nearest service centre immediately — "
                                      "a critical component is unhealthy."))

        # --- Component health based ---
        if vehicle.engine_health is not None and vehicle.engine_health < self.t.critical_component_health_threshold:
            recs.append(("Critical", "Engine service required urgently before travel."))
        elif vehicle.engine_health is not None and vehicle.engine_health < 65:
            recs.append(("High", "Engine service recommended before travel."))

        if vehicle.brake_health is not None and vehicle.brake_health < self.t.critical_component_health_threshold:
            recs.append(("Critical", "Brakes are critically worn — get them inspected before departure."))
        elif vehicle.brake_health is not None and vehicle.brake_health < 70:
            recs.append(("Medium", "Get brakes inspected before a long trip."))

        if vehicle.battery_health is not None and vehicle.battery_health < 65:
            recs.append(("Medium", "Battery health is low — carry jumper cables or get it tested."))

        if vehicle.tyre_health is not None and vehicle.tyre_health < 70:
            recs.append(("Medium", "Check tyre pressure and tread depth before departure."))

        # --- Digital twin status (Phase 4) ---
        if vehicle.digital_twin_status:
            for component, status in vehicle.digital_twin_status.items():
                if status.lower() in ("fault", "failed", "critical"):
                    recs.append(("Critical", f"Digital twin flags '{component}' as '{status}' — "
                                              f"do not travel until resolved."))
                elif status.lower() not in ("ok", "good", "healthy"):
                    recs.append(("Medium", f"Digital twin flags '{component}' as '{status}' — "
                                            f"inspect before departure."))

        # --- Active DTC codes (Phase 5) ---
        if vehicle.active_dtc_codes:
            codes = ", ".join(vehicle.active_dtc_codes)
            recs.append(("High", f"Active fault code(s) detected ({codes}) — visit service centre if unresolved."))

        # --- Pending maintenance (Phase 5/6) ---
        for item in (vehicle.pending_maintenance or []):
            recs.append(("Medium", f"Pending maintenance: {item}."))

        # --- Driver Behaviour (NEW) ---
        driver_score = vehicle.driver_behaviour_score
        if driver_score is None:
            driver_score = settings.default_driver_behaviour_score
        if driver_score < self.t.driver_behaviour_caution_min:
            recs.append(("High", "Driving behaviour has been aggressive (harsh braking/acceleration, "
                                  "overspeeding) — moderate driving style is strongly advised for this trip."))
        elif driver_score < self.t.driver_behaviour_go_min:
            recs.append(("Medium", "Driving behaviour has been moderately aggressive — "
                                    "avoid harsh braking, rapid acceleration, and overspeeding."))

        # --- Weather based ---
        if weather.rain_mm > 20:
            recs.append(("High", "Heavy rain expected — avoid the trip if possible or delay departure."))
        elif weather.rain_mm > 10 or "rain" in weather.condition.lower():
            recs.append(("Low", "Rain expected en route — carry an umbrella/raincoat and reduce speed."))
        if weather.wind_kph > 40:
            recs.append(("Medium", "Strong winds forecast — drive cautiously, especially on bridges/open highways."))
        if weather.alerts:
            recs.append(("High", "Severe weather alert active — monitor local advisories closely."))

        # --- Fuel based ---
        if not fuel.fuel_sufficient:
            recs.append(("High", f"Fuel is insufficient for the full trip — plan for "
                                  f"{fuel.refueling_stops_needed} refueling stop(s) en route."))
        elif fuel.fuel_available_l - fuel.fuel_required_l < 5:
            recs.append(("Medium", "Fuel margin is thin — refuel before departure as a safety buffer."))
        else:
            recs.append(("Low", "Fuel level is sufficient; refueling en route is optional."))

        # --- Route based ---
        if route.traffic_level and route.traffic_level.lower() == "heavy":
            recs.append(("Low", "Heavy traffic expected on the route — plan for extra travel time."))
        if route.distance_km > 400:
            recs.append(("Low", "Long-distance trip — plan rest breaks every 2 hours to avoid driver fatigue."))

        # De-duplicate by text while keeping the highest-priority occurrence
        best_priority_by_text = {}
        for priority, text in recs:
            if text not in best_priority_by_text or _PRIORITY_ORDER[priority] < _PRIORITY_ORDER[best_priority_by_text[text]]:
                best_priority_by_text[text] = priority

        items = [{"priority": p, "text": t} for t, p in best_priority_by_text.items()]

        if not items:
            items.append({"priority": "Low", "text": "No specific concerns detected. "
                                                       "Standard pre-trip checklist recommended."})

        # Sort by priority severity, preserving relative insertion order within a tier
        items.sort(key=lambda item: _PRIORITY_ORDER[item["priority"]])
        return items

    # ------------------------------------------------------------------ #
    @staticmethod
    def _has_critical_component_issue(vehicle: VehicleState) -> bool:
        """Used both here and by trip_engine.py to gate the Service Centre
        Recommendation — kept as a single source of truth."""
        threshold = risk_thresholds.critical_component_health_threshold
        component_scores = [
            vehicle.engine_health, vehicle.battery_health,
            vehicle.brake_health, vehicle.fuel_system_health, vehicle.tyre_health,
        ]
        if any(score is not None and score < threshold for score in component_scores):
            return True
        if vehicle.digital_twin_status:
            if any(status.lower() in ("fault", "failed", "critical")
                   for status in vehicle.digital_twin_status.values()):
                return True
        return False
