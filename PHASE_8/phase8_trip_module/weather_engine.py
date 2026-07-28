"""
weather_engine.py
Phase 8 - Trip Intelligence Module

Weather Engine
--------------
Fetches current weather for source, destination, and (optionally) route
midpoint using the OpenWeatherMap API. If no API key is configured or the
call fails, a deterministic mock generator is used instead so the module
always produces a result.

Also computes a normalized Weather Risk Score (0-100, higher = riskier)
that feeds directly into the Trip Risk Engine.
"""

from __future__ import annotations

import hashlib
import random
from typing import List, Optional, Tuple

import requests

from config import settings
from utils import clamp, get_logger

logger = get_logger(__name__)


class WeatherEngine:
    def __init__(self):
        self.mock_mode = settings.force_mock_weather or not settings.openweather_api_key

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get_weather(self, place: str, coords: Optional[Tuple[float, float]] = None) -> dict:
        """
        Returns dict: temperature_c, rain_mm, humidity_pct, wind_kph,
        condition, alerts, weather_risk_score, source_mode.
        """
        try:
            if self.mock_mode:
                return self._mock_weather(place)

            data = self._fetch_live(place, coords)
            if data is None:
                return self._mock_weather(place)
            return data

        except Exception as exc:  # noqa: BLE001
            logger.exception("Weather engine failure, falling back to mock: %s", exc)
            return self._mock_weather(place)

    def get_route_weather(
        self, source: str, destination: str
    ) -> dict:
        """Aggregate weather along the route (source + destination), returning the worse-case."""
        w_source = self.get_weather(source)
        w_dest = self.get_weather(destination)

        worse = w_source if w_source["weather_risk_score"] >= w_dest["weather_risk_score"] else w_dest
        combined_alerts = list(dict.fromkeys(w_source["alerts"] + w_dest["alerts"]))
        worse = dict(worse)
        worse["alerts"] = combined_alerts
        return worse

    # ------------------------------------------------------------------ #
    # Live data
    # ------------------------------------------------------------------ #
    def _fetch_live(self, place: str, coords: Optional[Tuple[float, float]]) -> Optional[dict]:
        try:
            params = {"appid": settings.openweather_api_key, "units": "metric"}
            if coords:
                params["lat"], params["lon"] = coords
            else:
                params["q"] = place

            resp = requests.get(f"{settings.openweather_base_url}/weather", params=params, timeout=6)
            resp.raise_for_status()
            data = resp.json()

            temperature_c = data["main"]["temp"]
            humidity_pct = data["main"]["humidity"]
            wind_kph = data["wind"]["speed"] * 3.6
            rain_mm = data.get("rain", {}).get("1h", 0.0)
            condition = data["weather"][0]["main"]
            alerts = [w["main"] for w in data.get("weather", []) if w["main"].lower() in
                      ("thunderstorm", "tornado", "squall")]

            risk_score = self._compute_risk_score(rain_mm, wind_kph, condition, alerts)

            return {
                "temperature_c": round(temperature_c, 1),
                "rain_mm": round(rain_mm, 1),
                "humidity_pct": round(humidity_pct, 1),
                "wind_kph": round(wind_kph, 1),
                "condition": condition,
                "alerts": alerts,
                "weather_risk_score": risk_score,
                "source_mode": "live",
            }
        except Exception as exc:  # noqa: BLE001
            logger.info("OpenWeather API unavailable (%s).", exc)
            return None

    # ------------------------------------------------------------------ #
    # Risk scoring
    # ------------------------------------------------------------------ #
    def _compute_risk_score(
        self, rain_mm: float, wind_kph: float, condition: str, alerts: List[str]
    ) -> float:
        score = 0.0
        score += clamp(rain_mm * 4.0, 0, 40)           # heavy rain contributes up to 40 pts
        score += clamp((wind_kph - 20) * 1.0, 0, 25)    # strong wind above 20kph contributes up to 25 pts
        if condition.lower() in ("thunderstorm", "snow", "tornado", "squall"):
            score += 25
        elif condition.lower() in ("rain", "drizzle", "mist", "fog"):
            score += 10
        if alerts:
            score += 20
        return round(clamp(score, 0, 100), 1)

    # ------------------------------------------------------------------ #
    # Mock fallback
    # ------------------------------------------------------------------ #
    def _mock_weather(self, place: str) -> dict:
        seed = int(hashlib.sha256(f"weather::{place}".encode()).hexdigest(), 16) % (10**6)
        rng = random.Random(seed)

        conditions = ["Clear", "Clouds", "Rain", "Drizzle", "Thunderstorm", "Haze"]
        condition = rng.choices(conditions, weights=[35, 30, 18, 8, 5, 4])[0]

        rain_mm = {
            "Clear": 0.0, "Clouds": 0.0, "Haze": 0.0,
            "Drizzle": round(rng.uniform(0.5, 3), 1),
            "Rain": round(rng.uniform(2, 15), 1),
            "Thunderstorm": round(rng.uniform(10, 40), 1),
        }[condition]

        wind_kph = round(rng.uniform(5, 45), 1)
        alerts = ["Heavy Rain Advisory"] if condition == "Thunderstorm" and rng.random() > 0.4 else []

        risk_score = self._compute_risk_score(rain_mm, wind_kph, condition, alerts)

        return {
            "temperature_c": round(rng.uniform(18, 38), 1),
            "rain_mm": rain_mm,
            "humidity_pct": round(rng.uniform(40, 95), 1),
            "wind_kph": wind_kph,
            "condition": condition,
            "alerts": alerts,
            "weather_risk_score": risk_score,
            "source_mode": "mock",
        }
