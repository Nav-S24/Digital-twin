"""
trip_engine.py
Phase 8 - Trip Intelligence Module

Trip Risk Engine + Orchestrator
--------------------------------
This is the central module that:
  1. Calls Route Engine, Weather Engine, Fuel Engine.
  2. Applies a configurable rule engine (see config.RiskThresholds) to
     classify the trip as GO / CAUTION / NO-GO.
  3. Calls the Recommendation Engine and LLM Explanation Engine.
  4. NEW: Calls the Service Centre Engine (when CAUTION/NO-GO or a critical
     component is unhealthy) and the Route Engine's alternate-route lookup
     (when severe weather or high composite risk is detected).
  5. NEW: Calls the Explainability Engine to build the "Why this
     recommendation?" panel.
  6. Assembles the final TripResponse consumed by the dashboard / API.

It does NOT retrain or re-run any ML models from Phases 2/3/5 — it only
*consumes* their outputs (vehicle health score, failure probability,
digital twin status, DTC codes) as inputs to trip-level decisioning.

CHANGE LOG (this revision):
  - TripRiskEngine's composite risk score now uses CONFIGURABLE weights
    (config.RiskThresholds.health_weight / failure_weight / weather_weight /
    driver_behaviour_weight) instead of hardcoded constants, per:
        Trip Risk = 40% Vehicle Health + 30% Failure Risk
                  + 15% Weather Risk + 15% Driver Behaviour Risk
  - NEW: Driver Behaviour Score (vehicle.driver_behaviour_score) is now a
    first-class input to both the composite risk score and the GO/CAUTION/
    NO-GO rule evaluation.
  - TripOrchestrator now also wires in ServiceCentreEngine,
    ExplainabilityEngine, and the RouteEngine's alternate-route lookup.
  - assess() and assess_trip() KEEP their original signatures — all new
    behaviour is additive.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from api.schemas import (
    ExplanationSummary,
    FuelEstimate,
    RecommendationItem,
    RiskAssessment,
    RouteInfo,
    ServiceCentreRecommendation,
    TripRequest,
    TripResponse,
    VehicleState,
    WeatherInfo,
)
from config import risk_thresholds, settings
from explainability_engine import ExplainabilityEngine
from fuel_engine import FuelEngine
from llm_engine import LLMEngine
from recommendation_engine import RecommendationEngine
from route_engine import RouteEngine
from service_centre_engine import ServiceCentreEngine
from utils import get_logger
from weather_engine import WeatherEngine

logger = get_logger(__name__)


class TripRiskEngine:
    """Configurable rule engine producing GO / CAUTION / NO-GO with a trace."""

    def __init__(self, thresholds=risk_thresholds):
        self.t = thresholds

    def assess(
        self,
        vehicle: VehicleState,
        weather: WeatherInfo,
        fuel: FuelEstimate,
        route: RouteInfo,
    ) -> RiskAssessment:
        trace: List[str] = []
        factors: List[str] = []

        health = vehicle.vehicle_health_score
        failure_p = vehicle.failure_probability
        rul_km = vehicle.remaining_useful_life_km or float("inf")
        weather_risk = weather.weather_risk_score
        driver_behaviour_score = vehicle.driver_behaviour_score
        if driver_behaviour_score is None:
            driver_behaviour_score = settings.default_driver_behaviour_score
        fuel_ok = fuel.fuel_sufficient or (
            fuel.fuel_available_l >= fuel.fuel_required_l / self.t.fuel_sufficiency_buffer
        )
        twin_critical = self._digital_twin_has_critical_fault(vehicle)
        twin_warning = self._digital_twin_has_warning(vehicle)
        active_faults = bool(vehicle.active_dtc_codes)

        trace.append(
            f"health={health:.1f} failure_p={failure_p:.2f} rul_km={rul_km:.0f} "
            f"weather_risk={weather_risk:.1f} driver_behaviour={driver_behaviour_score:.1f} "
            f"fuel_ok={fuel_ok} twin_critical={twin_critical} "
            f"twin_warning={twin_warning} active_faults={active_faults}"
        )

        # --- Composite numeric risk score (0-100, higher = riskier) ---
        # Trip Risk = health_weight*HealthRisk + failure_weight*FailureRisk
        #           + weather_weight*WeatherRisk + driver_behaviour_weight*DriverBehaviourRisk
        # (weights configurable via config.RiskThresholds; default 40/30/15/15)
        health_risk = 100 - health
        failure_risk = failure_p * 100
        driver_behaviour_risk = 100 - driver_behaviour_score

        risk_score = (
            self.t.health_weight * health_risk
            + self.t.failure_weight * failure_risk
            + self.t.weather_weight * weather_risk
            + self.t.driver_behaviour_weight * driver_behaviour_risk
        )
        # Additional binary-flag penalties for factors not part of the
        # weighted formula above (fuel logistics, digital twin, active faults).
        risk_score += (0 if fuel_ok else 20)
        risk_score += (15 if twin_critical else (7 if twin_warning else 0))
        risk_score += (10 if active_faults else 0)
        risk_score = round(min(100.0, risk_score), 1)

        trace.append(
            f"weighted_risk=health:{self.t.health_weight}*{health_risk:.1f} + "
            f"failure:{self.t.failure_weight}*{failure_risk:.1f} + "
            f"weather:{self.t.weather_weight}*{weather_risk:.1f} + "
            f"driver:{self.t.driver_behaviour_weight}*{driver_behaviour_risk:.1f} "
            f"-> composite={risk_score}"
        )

        # --- Rule evaluation, most severe (NO-GO) checked first ---
        no_go_reasons = []
        if health < self.t.health_caution_min:
            no_go_reasons.append(f"Vehicle health {health:.0f} is below minimum safe threshold "
                                  f"({self.t.health_caution_min:.0f}).")
        if failure_p > self.t.failure_caution_max:
            no_go_reasons.append(f"Failure probability {failure_p*100:.1f}% exceeds critical threshold "
                                  f"({self.t.failure_caution_max*100:.0f}%).")
        if rul_km < self.t.rul_caution_min_km:
            no_go_reasons.append(f"Remaining useful life {rul_km:.0f} km is critically low "
                                  f"(< {self.t.rul_caution_min_km:.0f} km).")
        if twin_critical:
            no_go_reasons.append("Digital twin reports a critical component fault.")
        if not fuel_ok and fuel.refueling_stops_needed > 2:
            no_go_reasons.append("Fuel shortfall requires more refueling stops than is practical.")
        if driver_behaviour_score < self.t.driver_behaviour_caution_min:
            no_go_reasons.append(f"Driver Behaviour Score {driver_behaviour_score:.0f} is critically low "
                                  f"(< {self.t.driver_behaviour_caution_min:.0f}) — pattern of unsafe driving.")

        if no_go_reasons:
            factors.extend(no_go_reasons)
            trace.append("Decision: NO-GO (critical threshold breach).")
            return RiskAssessment(
                trip_status="NO-GO",
                risk_score=risk_score,
                contributing_factors=factors,
                rule_trace=trace,
            )

        caution_reasons = []
        if health < self.t.health_go_min:
            caution_reasons.append(f"Vehicle health {health:.0f} is below ideal threshold "
                                    f"({self.t.health_go_min:.0f}).")
        if failure_p > self.t.failure_go_max:
            caution_reasons.append(f"Failure probability {failure_p*100:.1f}% is above the low-risk "
                                    f"threshold ({self.t.failure_go_max*100:.0f}%).")
        if weather_risk > self.t.weather_go_max:
            caution_reasons.append(f"Weather risk score {weather_risk:.0f} indicates non-trivial "
                                    f"conditions (rain/wind/alerts).")
        if rul_km < self.t.rul_go_min_km:
            caution_reasons.append(f"Remaining useful life {rul_km:.0f} km is moderate; monitor closely.")
        if not fuel_ok:
            caution_reasons.append("Fuel level requires at least one refueling stop en route.")
        if active_faults:
            caution_reasons.append("One or more active OBD fault codes are present.")
        if twin_warning:
            caution_reasons.append("Digital twin reports a component in Warning state.")
        if driver_behaviour_score < self.t.driver_behaviour_go_min:
            caution_reasons.append(f"Driver Behaviour Score {driver_behaviour_score:.0f} indicates "
                                    f"harsh braking/acceleration, idling, or overspeeding patterns.")
        if weather_risk > self.t.weather_caution_max:
            no_go_reasons.append(f"Severe weather risk score {weather_risk:.0f} exceeds safe travel limit.")

        # Re-check: severe weather escalates to NO-GO even if caught late
        if any("Severe weather" in r for r in no_go_reasons):
            factors.extend(caution_reasons + no_go_reasons)
            trace.append("Decision: NO-GO (severe weather escalation).")
            return RiskAssessment(
                trip_status="NO-GO",
                risk_score=risk_score,
                contributing_factors=factors,
                rule_trace=trace,
            )

        if caution_reasons:
            factors.extend(caution_reasons)
            trace.append("Decision: CAUTION (one or more moderate-risk factors).")
            return RiskAssessment(
                trip_status="CAUTION",
                risk_score=risk_score,
                contributing_factors=factors,
                rule_trace=trace,
            )

        factors.append("All health, failure-risk, weather, driver behaviour, and fuel checks passed comfortably.")
        trace.append("Decision: GO (all checks within safe thresholds).")
        return RiskAssessment(
            trip_status="GO",
            risk_score=risk_score,
            contributing_factors=factors,
            rule_trace=trace,
        )

    @staticmethod
    def _digital_twin_has_critical_fault(vehicle: VehicleState) -> bool:
        """True only for hard failures — these force an immediate NO-GO."""
        if not vehicle.digital_twin_status:
            return False
        critical_statuses = {"fault", "failed", "critical"}
        return any(status.lower() in critical_statuses for status in vehicle.digital_twin_status.values())

    @staticmethod
    def _digital_twin_has_warning(vehicle: VehicleState) -> bool:
        """True for soft Warning states — these contribute to CAUTION, not NO-GO."""
        if not vehicle.digital_twin_status:
            return False
        return any(status.lower() == "warning" for status in vehicle.digital_twin_status.values())


class TripOrchestrator:
    """Top-level entry point wiring together every Phase 8 sub-engine."""

    def __init__(self):
        self.route_engine = RouteEngine()
        self.weather_engine = WeatherEngine()
        self.fuel_engine = FuelEngine()
        self.risk_engine = TripRiskEngine()
        self.recommendation_engine = RecommendationEngine()
        self.llm_engine = LLMEngine()
        self.service_centre_engine = ServiceCentreEngine()          # NEW
        self.explainability_engine = ExplainabilityEngine()          # NEW

    def assess_trip(self, request: TripRequest) -> TripResponse:
        vehicle = request.vehicle
        logger.info("Assessing trip for vehicle=%s %s -> %s", vehicle.vehicle_id, request.source, request.destination)

        # 1. Route (now ORS-preferred, OSRM-alternative, mock-fallback — see route_engine.py)
        route_raw = self.route_engine.get_route(
            request.source, request.destination, request.source_coords, request.destination_coords
        )
        route = RouteInfo(**route_raw)

        # 2. Weather (worst of source/destination)
        weather_raw = self.weather_engine.get_route_weather(request.source, request.destination)
        weather = WeatherInfo(**weather_raw)

        # 3. Fuel
        fuel_raw = self.fuel_engine.estimate(
            distance_km=route.distance_km,
            mileage_kmpl=vehicle.mileage_kmpl,
            fuel_level_l=vehicle.fuel_level_l,
            tank_capacity_l=vehicle.fuel_tank_capacity_l or settings.default_fuel_tank_capacity_l,
            fuel_type=request.fuel_type,
        )
        fuel = FuelEstimate(**fuel_raw)

        # 4. Risk assessment (now includes Driver Behaviour Score)
        risk = self.risk_engine.assess(vehicle, weather, fuel, route)

        # 5. Prioritized recommendations (Critical/High/Medium/Low, sorted)
        recommendations_detailed_raw = self.recommendation_engine.generate_detailed(vehicle, weather, fuel, route)
        recommendations_detailed = [RecommendationItem(**item) for item in recommendations_detailed_raw]
        recommendations = [item.text for item in recommendations_detailed]  # backward-compatible List[str]

        # 6. NEW — Service Centre Recommendation: triggered by CAUTION/NO-GO
        #    OR a critical component being unhealthy (independent of trip status).
        service_centre_recommendation = self._maybe_recommend_service_centre(vehicle, risk, request)

        # 7. NEW — Alternate route suggestion: triggered by severe weather or high composite risk.
        alternate_route, alternate_route_reason = self._maybe_suggest_alternate_route(risk, weather, request)

        # 8. NEW — Explainable AI panel ("Why this recommendation?")
        explanation_raw = self.explainability_engine.explain(vehicle, weather, fuel, risk)
        explanation = ExplanationSummary(**explanation_raw)

        # 9. Natural language summary
        summary = self.llm_engine.explain(vehicle, route, weather, fuel, risk, recommendations)

        return TripResponse(
            vehicle_id=vehicle.vehicle_id,
            route=route,
            weather=weather,
            fuel=fuel,
            risk=risk,
            recommendations=recommendations,
            natural_language_summary=summary,
            recommendations_detailed=recommendations_detailed,
            service_centre_recommendation=service_centre_recommendation,
            alternate_route=alternate_route,
            alternate_route_reason=alternate_route_reason,
            explanation=explanation,
        )

    # ------------------------------------------------------------------ #
    # NEW helpers
    # ------------------------------------------------------------------ #
    def _maybe_recommend_service_centre(
        self, vehicle: VehicleState, risk: RiskAssessment, request: TripRequest
    ) -> Optional[ServiceCentreRecommendation]:
        critical_component = RecommendationEngine._has_critical_component_issue(vehicle)
        needs_service_centre = risk.trip_status in ("CAUTION", "NO-GO") or critical_component

        if not needs_service_centre:
            return None

        if critical_component:
            reason = "A critical vehicle component is unhealthy and needs inspection before further travel."
        else:
            reason = f"Trip status is {risk.trip_status} — a pre-trip check at a service centre is advised."

        current_coords: Optional[Tuple[float, float]] = None
        if request.source_coords:
            current_coords = (request.source_coords[0], request.source_coords[1])

        centre_raw = self.service_centre_engine.recommend(
            vehicle_id=vehicle.vehicle_id, reason=reason, current_coords=current_coords
        )
        if centre_raw is None:
            return None
        return ServiceCentreRecommendation(**centre_raw)

    def _maybe_suggest_alternate_route(
        self, risk: RiskAssessment, weather: WeatherInfo, request: TripRequest
    ) -> Tuple[Optional[RouteInfo], Optional[str]]:
        severe_weather = weather.weather_risk_score > risk_thresholds.weather_caution_max
        high_risk = risk.risk_score > risk_thresholds.alternate_route_risk_score_threshold

        if not (severe_weather or high_risk):
            return None, None

        if severe_weather:
            reason = (f"Weather risk score ({weather.weather_risk_score:.0f}/100) indicates severe conditions "
                       f"— an alternate route is suggested to avoid the worst-affected roads.")
        else:
            reason = (f"Composite trip risk score ({risk.risk_score:.0f}/100) is elevated — "
                       f"an alternate route is suggested as a lower-risk option.")

        alt_raw = self.route_engine.get_alternate_route(
            request.source, request.destination, request.source_coords, request.destination_coords
        )
        if alt_raw is None:
            return None, None
        return RouteInfo(**alt_raw), reason
