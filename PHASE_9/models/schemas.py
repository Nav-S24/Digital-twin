"""
models/schemas.py

Pydantic schemas for the Phase 9 REST API (Step 7). Keeping schemas
separate from route handlers keeps `api/main.py` thin and makes the
API self-documenting via FastAPI's automatic OpenAPI generation.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TripFeatures(BaseModel):
    veh_id: int
    trip_id: int
    global_trip_id: str
    trip_start_time: datetime
    trip_end_time: datetime
    avg_speed_kmh: float
    max_speed_kmh: float
    min_speed_kmh: float
    avg_acceleration_mps2: float
    max_acceleration_mps2: float
    avg_deceleration_mps2: float
    max_deceleration_mps2: float
    trip_duration_s: float
    distance_travelled_km: float
    idle_time_s: float
    stop_count: int
    num_accelerations: int
    num_harsh_brakes: int
    num_sharp_turns: int
    energy_consumption_kwh: float
    estimated_fuel_consumption_l: float
    fuel_efficiency_km_per_l: Optional[float] = None
    eco_driving_score: float
    highway_driving_pct: float
    city_driving_pct: float
    night_driving_pct: float
    peak_hour_driving_pct: float


class DriverScoreResponse(BaseModel):
    veh_id: int
    global_trip_id: Optional[str] = None
    driver_score: float = Field(..., ge=0, le=100)
    total_penalty: float
    total_bonus: float
    penalty_breakdown: Optional[Dict[str, float]] = None
    bonus_breakdown: Optional[Dict[str, float]] = None


class DriverProfileResponse(BaseModel):
    veh_id: int
    profile: str
    trip_count: int
    avg_score: Optional[float] = None
    total_distance_km: float
    profile_distribution: Optional[Dict[str, float]] = None


class CoachingCard(BaseModel):
    category: str
    message: str
    priority: str


class CoachingResponse(BaseModel):
    veh_id: int
    global_trip_id: Optional[str] = None
    cards: List[CoachingCard]
    narrative: Optional[str] = None
    source: str


class DriverStatisticsResponse(BaseModel):
    veh_id: int
    trip_count: int
    total_distance_km: float
    total_duration_hours: float
    avg_speed_kmh: float
    total_harsh_brakes: int
    total_aggressive_accelerations: int
    total_sharp_turns: int
    avg_fuel_efficiency_km_per_l: Optional[float] = None
    avg_eco_driving_score: float
    highway_driving_pct: float
    city_driving_pct: float
    night_driving_pct: float


class TripSummary(BaseModel):
    global_trip_id: str
    veh_id: int
    trip_id: int
    trip_start_time: datetime
    driver_score: float
    driver_profile: str
    distance_travelled_km: float
    trip_duration_s: float


class TripListResponse(BaseModel):
    veh_id: int
    trip_count: int
    trips: List[TripSummary]


class ErrorResponse(BaseModel):
    detail: str
    error_type: str
