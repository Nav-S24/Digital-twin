"""
api/schemas.py
Phase 8 - Trip Intelligence Module
Pydantic models defining the request/response contracts for the FastAPI service.
These mirror the outputs of Phase 2 (Health), Phase 3 (Failure Prediction),
Phase 4 (Digital Twin) and Phase 5/6 (Maintenance / DTC status).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class VehicleState(BaseModel):
    """Snapshot of a vehicle's current condition, sourced from Phases 2-6."""

    vehicle_id: str = Field(..., json_schema_extra={'example': "Vehicle_0001"})

    # Phase 2 - Vehicle Health Intelligence Engine
    vehicle_health_score: float = Field(..., ge=0, le=100, json_schema_extra={'example': 88.0})
    engine_health: Optional[float] = Field(default=None, ge=0, le=100)
    battery_health: Optional[float] = Field(default=None, ge=0, le=100)
    brake_health: Optional[float] = Field(default=None, ge=0, le=100)
    fuel_system_health: Optional[float] = Field(default=None, ge=0, le=100)
    tyre_health: Optional[float] = Field(default=None, ge=0, le=100)

    # Phase 3 - Predictive Maintenance & Failure Prediction
    failure_probability: float = Field(..., ge=0, le=1, json_schema_extra={'example': 0.12})
    remaining_useful_life_km: Optional[float] = Field(default=None, json_schema_extra={'example': 2480})

    # Phase 4 - Digital Twin
    digital_twin_status: Optional[Dict[str, str]] = Field(
        default=None, json_schema_extra={'example': {"engine": "OK", "battery": "OK", "brakes": "OK"}},
    )

    # Phase 5/6 - OBD Diagnostics / Maintenance History
    active_dtc_codes: Optional[List[str]] = Field(default_factory=list, json_schema_extra={'example': ["P0442"]})
    pending_maintenance: Optional[List[str]] = Field(default_factory=list)

    # Fuel / mileage
    fuel_level_l: float = Field(..., ge=0, json_schema_extra={'example': 42.0})
    fuel_tank_capacity_l: Optional[float] = Field(default=45.0)
    mileage_kmpl: float = Field(..., gt=0, json_schema_extra={'example': 18.0})

    # NEW: Driver Behaviour Score (0-100, higher = safer driving).
    # Derived from telematics: harsh braking, aggressive acceleration,
    # excessive idling, overspeeding. Optional — if not supplied, the Trip
    # Risk Engine falls back to config.settings.default_driver_behaviour_score
    # so existing callers that don't send this field keep working unchanged.
    driver_behaviour_score: Optional[float] = Field(default=None, ge=0, le=100, json_schema_extra={'example': 82.0})


class TripRequest(BaseModel):
    """Trip planning request combining vehicle state + trip parameters."""

    vehicle: VehicleState
    source: str = Field(..., json_schema_extra={'example': "Pune"})
    destination: str = Field(..., json_schema_extra={'example': "Mumbai"})
    source_coords: Optional[List[float]] = Field(default=None, json_schema_extra={'example': [18.5204, 73.8567]})
    destination_coords: Optional[List[float]] = Field(default=None, json_schema_extra={'example': [19.0760, 72.8777]})
    departure_time: Optional[str] = Field(default=None, json_schema_extra={'example': "2026-07-10T06:00:00"})
    fuel_type: str = Field(default="petrol", json_schema_extra={'example': "petrol"})


class RouteInfo(BaseModel):
    distance_km: float
    duration_min: float
    elevation_gain_m: Optional[float] = None
    traffic_level: Optional[str] = None
    coordinates: Optional[List[List[float]]] = None
    source_mode: str  # "live" or "mock"
    is_alternate: bool = False  # NEW: True when this RouteInfo represents an alternate route


class WeatherInfo(BaseModel):
    temperature_c: float
    rain_mm: float
    humidity_pct: float
    wind_kph: float
    condition: str
    alerts: List[str] = Field(default_factory=list)
    weather_risk_score: float
    source_mode: str


class FuelEstimate(BaseModel):
    fuel_required_l: float
    fuel_available_l: float
    fuel_sufficient: bool
    fuel_cost: float
    refueling_stops_needed: int
    price_per_litre: float
    source_mode: str


class RiskAssessment(BaseModel):
    trip_status: str  # GO / CAUTION / NO-GO
    risk_score: float  # 0-100, higher = riskier
    contributing_factors: List[str]
    rule_trace: List[str]


# --- NEW: Service Centre Recommendation --------------------------------- #
class ServiceCentreRecommendation(BaseModel):
    name: str
    address: str
    distance_km: float
    estimated_travel_time_min: float
    contact: Optional[str] = None
    reason: str
    source_mode: str  # "mock" for now; swappable for a real locator API later


# --- NEW: Prioritized recommendations ------------------------------------ #
class RecommendationItem(BaseModel):
    priority: str  # "Critical" | "High" | "Medium" | "Low"
    text: str


# --- NEW: Explainable AI panel ------------------------------------------- #
class ExplanationFactor(BaseModel):
    label: str  # e.g. "Vehicle Health"
    value: str  # e.g. "88% (Good)"
    status: str  # "Good" | "Moderate" | "Poor"


class ExplanationSummary(BaseModel):
    factors: List[ExplanationFactor]
    overall_statement: str  # e.g. "GO with caution because rain may reduce visibility."


class TripResponse(BaseModel):
    vehicle_id: str
    route: RouteInfo
    weather: WeatherInfo
    fuel: FuelEstimate
    risk: RiskAssessment
    recommendations: List[str]
    natural_language_summary: str

    # --- NEW fields (additive; existing consumers unaffected) ---
    recommendations_detailed: List[RecommendationItem] = Field(default_factory=list)
    service_centre_recommendation: Optional[ServiceCentreRecommendation] = None
    alternate_route: Optional[RouteInfo] = None
    alternate_route_reason: Optional[str] = None
    explanation: Optional[ExplanationSummary] = None
