"""
config/settings.py

Central configuration for Phase 9: Driver Behaviour Analytics.
All tunable thresholds, file paths, and constants live here so the rest
of the codebase never hardcodes a "magic number".

Values can be overridden via environment variables (see .env.example),
which makes the module deployable across different fleets / regions
without touching code.
"""

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _env_float(key: str, default: float) -> float:
    """Read a float from the environment, falling back to a default."""
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    """Read an int from the environment, falling back to a default."""
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _env_str(key: str, default: str) -> str:
    return os.getenv(key, default)


@dataclass(frozen=True)
class PathConfig:
    """File system locations used throughout the module."""

    base_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw_data_dir: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw"
    ))
    processed_data_dir: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "processed"
    ))
    features_dir: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "features"
    ))
    models_dir: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "artifacts"
    ))
    log_dir: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"
    ))


@dataclass(frozen=True)
class DetectionThresholds:
    """
    Behaviour-detection thresholds.

    Units:
        acceleration / deceleration -> m/s^2
        speed                       -> km/h
        idle                        -> seconds
        heading change              -> degrees / second
        lateral acceleration        -> m/s^2
    """

    aggressive_acceleration_mps2: float = _env_float("AGGRESSIVE_ACCEL_THRESHOLD", 2.5)
    harsh_braking_mps2: float = _env_float("HARSH_BRAKE_THRESHOLD", -3.0)
    idle_speed_kmh: float = _env_float("IDLE_SPEED_THRESHOLD", 1.0)
    excessive_idle_seconds: float = _env_float("EXCESSIVE_IDLE_SECONDS", 180.0)
    default_speed_limit_kmh: float = _env_float("DEFAULT_SPEED_LIMIT", 80.0)
    highway_speed_limit_kmh: float = _env_float("HIGHWAY_SPEED_LIMIT", 100.0)
    city_speed_limit_kmh: float = _env_float("CITY_SPEED_LIMIT", 60.0)
    overspeed_tolerance_kmh: float = _env_float("OVERSPEED_TOLERANCE", 5.0)
    rapid_heading_change_deg_s: float = _env_float("RAPID_HEADING_CHANGE", 8.0)
    sharp_corner_lateral_accel_mps2: float = _env_float("SHARP_CORNER_LATERAL_ACCEL", 3.0)
    highway_speed_floor_kmh: float = _env_float("HIGHWAY_SPEED_FLOOR", 80.0)
    city_speed_ceiling_kmh: float = _env_float("CITY_SPEED_CEILING", 60.0)
    night_start_hour: int = _env_int("NIGHT_START_HOUR", 21)
    night_end_hour: int = _env_int("NIGHT_END_HOUR", 5)
    peak_hours: List[int] = field(default_factory=lambda: [8, 9, 10, 17, 18, 19, 20])
    min_trip_points: int = _env_int("MIN_TRIP_POINTS", 10)
    min_trip_distance_km: float = _env_float("MIN_TRIP_DISTANCE_KM", 0.3)
    gps_jump_speed_kmh: float = _env_float("GPS_JUMP_SPEED_KMH", 200.0)


@dataclass(frozen=True)
class ScoringWeights:
    """Weights used by the DriverScorer to compute the 0-100 driver score."""

    base_score: float = 100.0

    # NOTE: these weights are applied to an "events per hour of driving"
    # rate, not to a raw event count or a distance-based rate. Distance
    # normalization (events per 100km) was tried first but systematically
    # over-penalizes slow, congested city driving: at low speed a driver
    # covers little distance per unit time, so a normal amount of
    # stop-and-go behaviour gets inflated into an extreme "rate" purely
    # because the denominator (km) is small -- it was flagging free-flowing
    # highway driving as safer than typical congested-city driving
    # regardless of actual behaviour. Time-based normalization does not
    # have that bias. Weights below are calibrated against the empirical
    # median/75th-percentile event-per-hour rates in the VED week-1
    # sample so a typical trip lands with a modest combined penalty
    # (~10-20 points) while high-rate outlier trips are pushed toward
    # the penalty cap.
    penalty_aggressive_acceleration: float = 0.15
    penalty_harsh_braking: float = 0.25
    penalty_overspeeding: float = 0.10
    penalty_excessive_idling: float = 2.00
    penalty_unsafe_cornering: float = 0.05
    penalty_rapid_lane_change: float = 0.20

    bonus_smooth_acceleration: float = 0.20
    bonus_consistent_speed: float = 2.00
    bonus_fuel_efficiency: float = 2.00
    bonus_low_idle_time: float = 2.00

    max_penalty_cap: float = 80.0
    # NOTE: base_score is already 100, i.e. "no penalty" already scores
    # perfectly. If bonuses can outweigh a typical trip's penalty, the
    # raw pre-clip score (100 - penalty + bonus) regularly exceeds 100
    # and gets clipped -- collapsing genuine differentiation among good
    # drivers into a pile-up at the ceiling (empirically ~28% of trips
    # in the VED week-1 sample before this was tightened). Bonus weights
    # above are calibrated so bonus nudges a trip's score up without
    # routinely overshooting 100 for anything short of a genuinely
    # clean trip.
    max_bonus_cap: float = 6.0


@dataclass(frozen=True)
class ProfileThresholds:
    """Score bands and behaviour-ratio bands used to assign driver profiles."""

    eco_driver_min_score: float = 75.0
    # Both "Safe Driver" and "Eco Driver" are assigned at this same score
    # floor -- the split between them is the fuel-efficiency check in
    # DriverProfiler.classify_trip, not a separate score band.
    normal_driver_min_score: float = 55.0
    aggressive_driver_min_score: float = 35.0
    # anything below aggressive_driver_min_score => High Risk Driver

    eco_min_fuel_efficiency_km_per_l: float = 12.0
    high_risk_events_per_hour: float = 120.0


@dataclass(frozen=True)
class VehicleConfig:
    """Assumptions used to translate OBD signals into fuel/energy estimates."""

    fuel_density_kg_per_l: float = 0.745  # gasoline
    default_engine_displacement_l: float = 2.0
    afr_stoichiometric: float = 14.7  # air-fuel ratio used for MAF -> fuel rate fallback


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for the coaching / summarization LLM integration."""

    provider: str = _env_str("LLM_PROVIDER", "anthropic")  # "anthropic" or "openai"
    anthropic_api_key: str = _env_str("ANTHROPIC_API_KEY", "")
    openai_api_key: str = _env_str("OPENAI_API_KEY", "")
    anthropic_model: str = _env_str("ANTHROPIC_MODEL", "claude-sonnet-5")
    openai_model: str = _env_str("OPENAI_MODEL", "gpt-4o-mini")
    max_tokens: int = _env_int("LLM_MAX_TOKENS", 800)
    temperature: float = _env_float("LLM_TEMPERATURE", 0.4)
    request_timeout_seconds: int = _env_int("LLM_TIMEOUT", 30)


@dataclass(frozen=True)
class APIConfig:
    """FastAPI server configuration."""

    host: str = _env_str("API_HOST", "0.0.0.0")
    port: int = _env_int("API_PORT", 8009)
    title: str = "Phase 9 - Driver Behaviour Analytics API"
    version: str = "1.0.0"


@dataclass(frozen=True)
class DashboardConfig:
    """Streamlit dashboard configuration."""

    page_title: str = "Driver Behaviour Analytics - Tata Motors"
    page_icon: str = "🚗"
    layout: str = "wide"


PATHS = PathConfig()
THRESHOLDS = DetectionThresholds()
SCORING = ScoringWeights()
PROFILES = ProfileThresholds()
VEHICLE = VehicleConfig()
LLM = LLMConfig()
API = APIConfig()
DASHBOARD = DashboardConfig()

# Behaviour category labels, defined once and reused everywhere to avoid
# typos / inconsistent strings across modules.
PROFILE_LABELS = {
    "SAFE": "Safe Driver",
    "ECO": "Eco Driver",
    "NORMAL": "Normal Driver",
    "AGGRESSIVE": "Aggressive Driver",
    "HIGH_RISK": "High Risk Driver",
}

VED_RAW_COLUMNS = [
    "DayNum", "VehId", "Trip", "Timestamp(ms)", "Latitude[deg]", "Longitude[deg]",
    "Vehicle Speed[km/h]", "MAF[g/sec]", "Engine RPM[RPM]", "Absolute Load[%]",
    "OAT[DegC]", "Fuel Rate[L/hr]", "Air Conditioning Power[kW]",
    "Air Conditioning Power[Watts]", "Heater Power[Watts]", "HV Battery Current[A]",
    "HV Battery SOC[%]", "HV Battery Voltage[V]", "Short Term Fuel Trim Bank 1[%]",
    "Short Term Fuel Trim Bank 2[%]", "Long Term Fuel Trim Bank 1[%]",
    "Long Term Fuel Trim Bank 2[%]",
]
