"""
config.py
Phase 8 - Trip Intelligence Module
Centralized configuration using pydantic-settings.

All thresholds for the Trip Risk Engine are exposed here so the
rule engine is fully configurable without touching business logic.
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    from pydantic import Field
except ImportError:  # graceful fallback if pydantic-settings isn't installed
    from pydantic import BaseSettings, Field  # type: ignore
    SettingsConfigDict = dict  # type: ignore


class RiskThresholds(BaseSettings):
    """Configurable thresholds that drive the GO / CAUTION / NO-GO decision."""

    # --- Composite Trip Risk weights (must sum to ~1.0; fully configurable) ---
    # Trip Risk = health_weight*HealthRisk + failure_weight*FailureRisk
    #           + weather_weight*WeatherRisk + driver_behaviour_weight*DriverBehaviourRisk
    health_weight: float = 0.40
    failure_weight: float = 0.30
    weather_weight: float = 0.15
    driver_behaviour_weight: float = 0.15

    # Vehicle health score thresholds (0-100)
    health_go_min: float = 80.0
    health_caution_min: float = 60.0

    # Failure probability thresholds (0-1)
    failure_go_max: float = 0.20
    failure_caution_max: float = 0.45

    # Weather risk score thresholds (0-100, higher = worse)
    weather_go_max: float = 30.0
    weather_caution_max: float = 65.0

    # Driver Behaviour Score thresholds (0-100, higher = safer driving)
    driver_behaviour_go_min: float = 75.0
    driver_behaviour_caution_min: float = 50.0

    # Fuel sufficiency buffer (fraction of trip fuel requirement that must
    # be available onboard, e.g. 1.1 = require 10% buffer over exact need)
    fuel_sufficiency_buffer: float = 1.1

    # RUL (remaining useful life) thresholds in km
    rul_go_min_km: float = 500.0
    rul_caution_min_km: float = 150.0

    # Composite risk score above which an alternate route is proactively suggested
    alternate_route_risk_score_threshold: float = 55.0

    # Component health below which a component is considered "critical unhealthy"
    # (used to trigger the Service Centre Recommendation independent of trip status)
    critical_component_health_threshold: float = 50.0

    model_config = SettingsConfigDict(env_prefix="RISK_")


class Settings(BaseSettings):
    """Global application settings."""

    app_name: str = "Phase 8 - Trip Intelligence Module"
    debug: bool = True

    # --- External API keys (optional; module runs in MOCK mode if absent) ---
    # Field names below are matched case-insensitively to env vars of the
    # same name by pydantic-settings (e.g. openweather_api_key <- OPENWEATHER_API_KEY).
    openweather_api_key: Optional[str] = None
    fuel_price_api_key: Optional[str] = None
    ors_api_key: Optional[str] = None  # OpenRouteService
    llm_api_key: Optional[str] = Field(default=None,validation_alias="GOOGLE_API_KEY")

    # --- Mock mode toggles (auto-enabled when the relevant key is missing) ---
    force_mock_weather: bool = False
    force_mock_fuel: bool = False
    force_mock_route: bool = False
    force_mock_llm: bool = False

    # --- Endpoints ---
    openweather_base_url: str = "https://api.openweathermap.org/data/2.5"
    ors_base_url: str = "https://api.openrouteservice.org/v2"
    osrm_public_base_url: str = "https://router.project-osrm.org"  # free, no key, used as OSM fallback
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"

    # --- Integration paths: outputs from earlier phases ---
    phase3_predictions_csv: str = os.path.join("data", "Phase3_Predictions.csv")
    phase5_diagnostic_csv: str = os.path.join("data", "phase5_diagnostic_output.csv")

    # --- Service Centre Recommendation (mocked / JSON-backed for now) ---
    service_centre_data_path: str = os.path.join("data", "service_centres.json")

    # --- Default assumptions ---
    default_mileage_kmpl: float = 15.0
    default_fuel_tank_capacity_l: float = 45.0
    default_driver_behaviour_score: float = 90.0  # assumed "good" if not supplied
    currency_symbol: str = "₹"

    # --- Logging ---
    log_dir: str = "logs"
    log_file: str = "trip_module.log"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="")


settings = Settings()
risk_thresholds = RiskThresholds()
