"""
config/settings.py
==================
Central configuration for the Vehicle Digital Twin platform.
All tunable constants, thresholds, paths, and service settings
live here so that no magic numbers are scattered across the codebase.
"""

from pathlib import Path
from typing import Dict, Tuple

# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DATA_DIR          = BASE_DIR / "data"
PHASE2_CSV        = DATA_DIR / "phase2_output" / "Output-phase2.csv"
PHASE3_CSV        = DATA_DIR / "phase3_output" / "Phase3_Predictions.csv"
NASA_CMAPSS_DIR   = DATA_DIR / "nasa_cmapss"
MERGED_CSV        = DATA_DIR / "merged_vehicle_state.csv"

# ---------------------------------------------------------------------------
# API settings
# ---------------------------------------------------------------------------
API_HOST          = "0.0.0.0"
API_PORT          = 8000
API_TITLE         = "Vehicle Digital Twin API"
API_VERSION       = "1.0.0"
API_DESCRIPTION   = (
    "REST API for the Vehicle Digital Twin platform. "
    "Exposes vehicle state, component health, failure predictions, "
    "RUL estimates, historical trends, and future degradation simulations."
)
CORS_ORIGINS = [
    "http://localhost:3000",   # React dev server
    "http://127.0.0.1:3000",
    "http://localhost:5173",   # Vite dev server
]

# ---------------------------------------------------------------------------
# Sensor column mapping (Phase 2 CSV → internal canonical names)
# ---------------------------------------------------------------------------
SENSOR_COLUMNS: Dict[str, str] = {
    "temperature":      "engine_temperature",
    "pressure":         "engine_pressure",
    "rpm":              "engine_rpm",
    "vibration":        "engine_vibration",
    "battery_voltage":  "battery_voltage",
    "battery_current":  "battery_current",
    "battery_temp":     "battery_temperature",
    "fault_count":      "fault_count",
}

# ---------------------------------------------------------------------------
# Sensor operating thresholds (derived from dataset statistics)
# Values used to normalise raw readings into 0-100 health sub-scores
# ---------------------------------------------------------------------------
SENSOR_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "engine_temperature": {
        "min": 44.5,
        "optimal_low": 70.0,
        "optimal_high": 95.0,
        "max": 125.0,
        "critical": 115.0,
    },
    "engine_pressure": {
        "min": 13.8,
        "optimal_low": 24.0,
        "optimal_high": 36.0,
        "max": 47.0,
        "critical": 44.0,
    },
    "engine_rpm": {
        "min": 500.0,
        "optimal_low": 800.0,
        "optimal_high": 3500.0,
        "max": 4700.0,
        "critical": 4500.0,
    },
    "engine_vibration": {
        "min": 0.0,
        "optimal_low": 0.0,
        "optimal_high": 0.35,
        "max": 0.75,
        "critical": 0.60,
    },
    "battery_voltage": {
        "min": 11.0,
        "optimal_low": 12.0,
        "optimal_high": 13.2,
        "max": 14.0,
        "critical": 11.5,
    },
    "battery_current": {
        "min": 0.0,
        "optimal_low": 10.0,
        "optimal_high": 80.0,
        "max": 110.0,
        "critical": 100.0,
    },
    "battery_temperature": {
        "min": 10.0,
        "optimal_low": 15.0,
        "optimal_high": 45.0,
        "max": 65.0,
        "critical": 58.0,
    },
    "fault_count": {
        "min": 0.0,
        "optimal_low": 0.0,
        "optimal_high": 2.0,
        "max": 10.0,
        "critical": 7.0,
    },
}

# ---------------------------------------------------------------------------
# Health classification thresholds
# ---------------------------------------------------------------------------
HEALTH_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    # label: (lower_bound_inclusive, upper_bound_inclusive)
    "Excellent": (85.0, 100.0),
    "Good":      (65.0,  84.9),
    "Warning":   (40.0,  64.9),
    "Critical":  (0.0,   39.9),
}

HEALTH_CLASS_COLORS: Dict[str, str] = {
    "Excellent": "#00d4aa",   # teal-green
    "Good":      "#4ade80",   # green
    "Warning":   "#facc15",   # amber
    "Critical":  "#ef4444",   # red
}

# ---------------------------------------------------------------------------
# Fuel Health scoring weights
# Fuel Health is derived from engine sensors (no direct fuel dataset).
# Each factor contributes a weighted penalty to the base score of 100.
# Algorithm documented in twin/fuel.py.
# ---------------------------------------------------------------------------
FUEL_HEALTH_WEIGHTS: Dict[str, float] = {
    "temperature_factor":  0.30,   # high temp → fuel stress
    "pressure_factor":     0.25,   # low pressure → lean mixture
    "rpm_factor":          0.20,   # sustained high RPM → excess consumption
    "vibration_factor":    0.15,   # vibration → injector wear proxy
    "fault_factor":        0.10,   # fault codes → ECU-detected fuel faults
}

# Fuel health degrades at this rate per simulation day (% per day)
FUEL_DEGRADATION_RATE_PER_DAY: float = 0.08

# ---------------------------------------------------------------------------
# Brake Health scoring
# No brake dataset exists; synthetic estimation from vehicle usage proxies.
# Assumptions documented in twin/brake.py.
# ---------------------------------------------------------------------------
BRAKE_INITIAL_PAD_LIFE_KM:     float = 40_000.0   # typical pad life
BRAKE_DEGRADATION_PER_KM:      float = 100.0 / 40_000.0   # linear wear rate
BRAKE_HARD_BRAKING_PENALTY:    float = 0.05   # % penalty per hard-brake event
BRAKE_DEGRADATION_RATE_PER_DAY: float = 0.10  # simulation daily decay

# ---------------------------------------------------------------------------
# Simulation settings
# ---------------------------------------------------------------------------
SIMULATION_HORIZONS_DAYS = [30, 60, 90, 180, 365]

# Linear daily degradation rates (% health lost per day) per component.
# These represent average fleet degradation and are overridden when
# NASA CMAPSS data is available for the engine.
DEFAULT_DEGRADATION_RATES: Dict[str, float] = {
    "engine":  0.05,
    "battery": 0.03,
    "fuel":    0.08,
    "brake":   0.10,
    "vehicle": 0.06,
}

# ---------------------------------------------------------------------------
# Pagination defaults for API list endpoints
# ---------------------------------------------------------------------------
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE     = 500

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL  = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
