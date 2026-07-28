"""
llm_engine.py
Phase 8 - Trip Intelligence Module

LLM Explanation Engine
-----------------------
Turns the structured outputs of the Route/Weather/Fuel/Risk engines into a
natural-language trip summary. Uses the Anthropic Claude API if a key is
configured (ANTHROPIC_API_KEY); otherwise falls back to a deterministic
template-based generator so the module runs fully offline.
"""

from __future__ import annotations

from typing import List

from api.schemas import FuelEstimate, RiskAssessment, RouteInfo, VehicleState, WeatherInfo
from config import settings
from utils import format_currency, get_logger

logger = get_logger(__name__)


class LLMEngine:
    def __init__(self):
        self.mock_mode = settings.force_mock_llm or not settings.llm_api_key
        self._client = None
        if not self.mock_mode:
            try:
                import anthropic  # imported lazily; optional dependency
                self._client = anthropic.Anthropic(api_key=settings.llm_api_key)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Anthropic SDK unavailable (%s); using template fallback.", exc)
                self.mock_mode = True

    def explain(
        self,
        vehicle: VehicleState,
        route: RouteInfo,
        weather: WeatherInfo,
        fuel: FuelEstimate,
        risk: RiskAssessment,
        recommendations: List[str],
    ) -> str:
        if self.mock_mode:
            return self._template_summary(vehicle, route, weather, fuel, risk, recommendations)

        try:
            prompt = self._build_prompt(vehicle, route, weather, fuel, risk, recommendations)
            response = self._client.messages.create(
                model="claude-sonnet-5",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            text_blocks = [b.text for b in response.content if getattr(b, "type", "") == "text"]
            return "\n".join(text_blocks).strip() or self._template_summary(
                vehicle, route, weather, fuel, risk, recommendations
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM call failed, using template fallback: %s", exc)
            return self._template_summary(vehicle, route, weather, fuel, risk, recommendations)

    # ------------------------------------------------------------------ #
    def _build_prompt(
        self,
        vehicle: VehicleState,
        route: RouteInfo,
        weather: WeatherInfo,
        fuel: FuelEstimate,
        risk: RiskAssessment,
        recommendations: List[str],
    ) -> str:
        return (
            "You are a vehicle trip-readiness assistant. Write a short, warm, "
            "conversational summary (4-6 sentences) for a driver based on this data. "
            "Do not invent numbers beyond what's given.\n\n"
            f"Vehicle health score: {vehicle.vehicle_health_score}\n"
            f"Failure probability: {vehicle.failure_probability*100:.1f}%\n"
            f"Route: {route.distance_km} km, {route.duration_min} min\n"
            f"Weather: {weather.condition}, rain {weather.rain_mm}mm, wind {weather.wind_kph}kph\n"
            f"Fuel required: {fuel.fuel_required_l} L, available: {fuel.fuel_available_l} L, "
            f"cost: {format_currency(fuel.fuel_cost)}\n"
            f"Trip status: {risk.trip_status} (risk score {risk.risk_score}/100)\n"
            f"Top recommendations: {'; '.join(recommendations[:3])}\n"
        )

    # ------------------------------------------------------------------ #
    def _template_summary(
        self,
        vehicle: VehicleState,
        route: RouteInfo,
        weather: WeatherInfo,
        fuel: FuelEstimate,
        risk: RiskAssessment,
        recommendations: List[str],
    ) -> str:
        status = risk.trip_status
        opening = {
            "GO": "Your vehicle is ready for the trip.",
            "CAUTION": "Your vehicle can make the trip, but a few things need attention.",
            "NO-GO": "This trip is not recommended right now.",
        }[status]

        lines = [opening, f"Vehicle health is {vehicle.vehicle_health_score:.0f}%."]

        if vehicle.failure_probability < 0.15:
            lines.append("The engine and key components are performing normally.")
        elif vehicle.failure_probability < 0.45:
            lines.append(f"Failure probability is elevated at {vehicle.failure_probability*100:.0f}%, "
                          "so keep an eye on warning signs.")
        else:
            lines.append(f"Failure probability is high at {vehicle.failure_probability*100:.0f}%, "
                          "which is a significant concern.")

        if fuel.fuel_sufficient:
            lines.append("Fuel is sufficient for the planned journey.")
        else:
            lines.append(f"Fuel is not sufficient; plan for {fuel.refueling_stops_needed} "
                          "refueling stop(s) en route.")

        if weather.rain_mm > 0 or weather.condition.lower() not in ("clear", "clouds"):
            lines.append(f"{weather.condition} is expected along the route "
                          f"({weather.rain_mm}mm rain, {weather.wind_kph}kph wind).")
        else:
            lines.append("Weather conditions along the route look favorable.")

        lines.append(f"Estimated fuel cost is {format_currency(fuel.fuel_cost)} "
                      f"over {route.distance_km} km.")

        if recommendations:
            lines.append("Key recommendation: " + recommendations[0])

        lines.append(f"Overall recommendation: {status}.")

        return " ".join(lines)
