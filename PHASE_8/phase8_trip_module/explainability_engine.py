"""
explainability_engine.py
Phase 8 - Trip Intelligence Module

NEW MODULE (this revision)
---------------------------
Explainable AI Panel — "Why this recommendation?"
---------------------------------------------------
Turns the same structured outputs already used by the Trip Risk Engine into
a short, plain-language explanation: one line per contributing factor
(Vehicle Health, Failure Risk, Weather, Driver Behaviour, Fuel) plus a
single overall statement tying the GO/CAUTION/NO-GO decision to the most
relevant reason — mirroring the exact style requested in the spec:

    Vehicle Health: 88% (Good)
    Failure Risk: Low
    Weather: Moderate Rain
    Driver Behaviour: Aggressive
    Fuel: Sufficient
    Overall recommendation: GO with caution because rain may reduce visibility.

This is intentionally rule-based (no extra ML/LLM call) so the explanation
is always available instantly and is fully auditable — it reuses the same
thresholds as trip_engine.TripRiskEngine so the panel never contradicts the
GO/CAUTION/NO-GO badge.
"""

from __future__ import annotations

from typing import List

from api.schemas import FuelEstimate, RiskAssessment, VehicleState, WeatherInfo
from config import risk_thresholds, settings


class ExplainabilityEngine:
    def __init__(self, thresholds=risk_thresholds):
        self.t = thresholds

    def explain(
        self,
        vehicle: VehicleState,
        weather: WeatherInfo,
        fuel: FuelEstimate,
        risk: RiskAssessment,
    ) -> dict:
        """Returns dict: {factors: [{label, value, status}], overall_statement: str}"""
        factors = [
            self._health_factor(vehicle),
            self._failure_factor(vehicle),
            self._weather_factor(weather),
            self._driver_behaviour_factor(vehicle),
            self._fuel_factor(fuel),
        ]

        overall_statement = self._overall_statement(vehicle, weather, fuel, risk)

        return {"factors": factors, "overall_statement": overall_statement}

    # ------------------------------------------------------------------ #
    def _health_factor(self, vehicle: VehicleState) -> dict:
        health = vehicle.vehicle_health_score
        if health >= self.t.health_go_min:
            status = "Good"
        elif health >= self.t.health_caution_min:
            status = "Moderate"
        else:
            status = "Poor"
        return {"label": "Vehicle Health", "value": f"{health:.0f}% ({status})", "status": status}

    def _failure_factor(self, vehicle: VehicleState) -> dict:
        p = vehicle.failure_probability
        if p <= self.t.failure_go_max:
            label, status = "Low", "Good"
        elif p <= self.t.failure_caution_max:
            label, status = "Moderate", "Moderate"
        else:
            label, status = "High", "Poor"
        return {"label": "Failure Risk", "value": label, "status": status}

    def _weather_factor(self, weather: WeatherInfo) -> dict:
        risk = weather.weather_risk_score
        descriptor = weather.condition
        if weather.rain_mm > 0:
            descriptor = f"{weather.condition} ({weather.rain_mm}mm rain)"
        if risk <= self.t.weather_go_max:
            status = "Good"
        elif risk <= self.t.weather_caution_max:
            status = "Moderate"
        else:
            status = "Poor"
        return {"label": "Weather", "value": descriptor, "status": status}

    def _driver_behaviour_factor(self, vehicle: VehicleState) -> dict:
        score = vehicle.driver_behaviour_score
        if score is None:
            score = settings.default_driver_behaviour_score
        if score >= self.t.driver_behaviour_go_min:
            label, status = "Safe", "Good"
        elif score >= self.t.driver_behaviour_caution_min:
            label, status = "Moderate", "Moderate"
        else:
            label, status = "Aggressive", "Poor"
        return {"label": "Driver Behaviour", "value": f"{label} ({score:.0f}/100)", "status": status}

    def _fuel_factor(self, fuel: FuelEstimate) -> dict:
        if fuel.fuel_sufficient:
            return {"label": "Fuel", "value": "Sufficient", "status": "Good"}
        return {
            "label": "Fuel",
            "value": f"Insufficient — {fuel.refueling_stops_needed} stop(s) needed",
            "status": "Poor",
        }

    # ------------------------------------------------------------------ #
    def _overall_statement(
        self, vehicle: VehicleState, weather: WeatherInfo, fuel: FuelEstimate, risk: RiskAssessment
    ) -> str:
        status = risk.trip_status

        # Pick the single most relevant caveat to surface, prioritizing the
        # first contributing factor already computed by the Trip Risk Engine.
        caveat = None
        if weather.rain_mm > 5 or "rain" in weather.condition.lower():
            caveat = "rain may reduce visibility"
        elif weather.wind_kph > 40:
            caveat = "strong winds may affect vehicle stability"
        elif vehicle.driver_behaviour_score is not None and vehicle.driver_behaviour_score < self.t.driver_behaviour_go_min:
            caveat = "recent driving behaviour has been aggressive"
        elif not fuel.fuel_sufficient:
            caveat = "fuel will need to be topped up en route"
        elif vehicle.failure_probability > self.t.failure_go_max:
            caveat = "failure probability is elevated"
        elif status != "GO" and risk.contributing_factors:
            caveat = risk.contributing_factors[0].rstrip(".").lower()

        if status == "GO" and caveat:
            return f"GO with caution because {caveat}."
        if status == "GO":
            return "GO — all systems and conditions are within safe limits."
        if status == "CAUTION":
            return f"CAUTION — trip is possible, but {caveat or 'some factors need attention'}."
        return f"NO-GO — trip is not recommended because {caveat or 'critical risk factors were detected'}."
