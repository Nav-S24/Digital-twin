"""
utils/models.py
===============
Pydantic v2 data models (schemas) shared by the twin layer, service layer,
and FastAPI endpoints. Separating schemas from business logic keeps the
codebase testable and database-ready for future integration.

Design principles
-----------------
* Every numeric health score is in the range [0, 100].
* Every probability is in the range [0.0, 1.0].
* Timestamps are ISO-8601 strings to survive JSON serialisation cleanly.
* All models use `model_config = ConfigDict(from_attributes=True)` so they
  can be constructed from ORM objects when a database layer is added later.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Sensor snapshot
# ---------------------------------------------------------------------------

class SensorSnapshot(BaseModel):
    """Raw sensor readings for a single vehicle at a point in time."""
    model_config = ConfigDict(from_attributes=True)

    vehicle_id:          str
    timestamp:           str

    # Engine sensors
    engine_temperature:  float = Field(..., description="°C")
    engine_pressure:     float = Field(..., description="bar")
    engine_rpm:          float = Field(..., description="RPM")
    engine_vibration:    float = Field(..., description="g")

    # Battery sensors
    battery_voltage:     float = Field(..., description="V")
    battery_current:     float = Field(..., description="A")
    battery_temperature: float = Field(..., description="°C")

    # Misc
    fault_count:         float = Field(..., description="OBD-II active DTCs")


# ---------------------------------------------------------------------------
# Component-level twin states
# ---------------------------------------------------------------------------

class EngineState(BaseModel):
    """Current state of the Engine Digital Twin."""
    model_config = ConfigDict(from_attributes=True)

    vehicle_id:              str
    timestamp:               str

    # Live sensor values
    temperature:             float = Field(..., description="°C")
    pressure:                float = Field(..., description="bar")
    rpm:                     float = Field(..., description="RPM")
    vibration:               float = Field(..., description="g")

    # Health & risk (sourced from Phase 2 + Phase 3)
    health_score:            float = Field(..., ge=0, le=100)
    failure_probability:     float = Field(..., ge=0, le=1)
    remaining_useful_life_cycles: int    = Field(..., ge=0)
    remaining_useful_life_km:     int    = Field(..., ge=0)

    # Classification & recommendations
    health_status:           str   = Field(..., description="Excellent/Good/Warning/Critical")
    maintenance_recommendation: str
    top_risk_sensor:         Optional[str] = None
    shap_explanation:        Optional[str] = None
    affected_system:         Optional[str] = None

    # Historical buffer sizes
    history_length:          int = 0


class BatteryState(BaseModel):
    """Current state of the Battery Digital Twin."""
    model_config = ConfigDict(from_attributes=True)

    vehicle_id:              str
    timestamp:               str

    # Live sensor values
    voltage:                 float = Field(..., description="V")
    current:                 float = Field(..., description="A")
    temperature:             float = Field(..., description="°C")

    # Derived (Phase 2 + Phase 3)
    health_score:            float = Field(..., ge=0, le=100)
    failure_probability:     float = Field(..., ge=0, le=1)
    remaining_useful_life_cycles: int = Field(..., ge=0)
    remaining_useful_life_km:     int = Field(..., ge=0)

    # State-of-Charge and State-of-Health estimates
    state_of_charge:         float = Field(..., ge=0, le=100, description="%")
    state_of_health:         float = Field(..., ge=0, le=100, description="%")

    health_status:           str
    maintenance_recommendation: str

    history_length:          int = 0


class FuelState(BaseModel):
    """
    Current state of the Fuel System Digital Twin.
    Fuel health is derived — not directly predicted — using engine sensor
    values. See twin/fuel.py for the full scoring algorithm.
    """
    model_config = ConfigDict(from_attributes=True)

    vehicle_id:   str
    timestamp:    str

    # Derived health score (0–100)
    health_score: float = Field(..., ge=0, le=100)
    health_status: str

    # Sensor inputs used in scoring
    temperature_contribution: float = Field(..., description="Temperature sub-score [0–100]")
    pressure_contribution:    float = Field(..., description="Pressure sub-score [0–100]")
    rpm_contribution:         float = Field(..., description="RPM sub-score [0–100]")
    vibration_contribution:   float = Field(..., description="Vibration sub-score [0–100]")
    fault_contribution:       float = Field(..., description="Fault sub-score [0–100]")

    # Risk
    failure_probability:      float = Field(..., ge=0, le=1)
    maintenance_recommendation: str

    history_length: int = 0


class BrakeState(BaseModel):
    """
    Current state of the Brake System Digital Twin.
    No brake dataset is available. Brake health is estimated synthetically
    from mileage proxy (RUL_KM as a wear surrogate) and fault count.
    See twin/brake.py for assumptions.
    """
    model_config = ConfigDict(from_attributes=True)

    vehicle_id:   str
    timestamp:    str

    health_score: float = Field(..., ge=0, le=100)
    health_status: str

    # Synthetic wear estimation inputs
    estimated_mileage_km:     float = Field(..., description="Proxy mileage from RUL_KM")
    pad_wear_percentage:      float = Field(..., ge=0, le=100, description="% pad worn")
    hard_brake_event_count:   int   = Field(..., ge=0)

    failure_probability:      float = Field(..., ge=0, le=1)
    maintenance_recommendation: str

    history_length: int = 0


# ---------------------------------------------------------------------------
# Vehicle-level twin state (aggregates all components)
# ---------------------------------------------------------------------------

class VehicleState(BaseModel):
    """Aggregated state of the full Vehicle Digital Twin."""
    model_config = ConfigDict(from_attributes=True)

    vehicle_id:          str
    timestamp:           str

    # Overall health (weighted average of components)
    overall_health:          float = Field(..., ge=0, le=100)
    overall_failure_probability: float = Field(..., ge=0, le=1)
    overall_rul_cycles:      int
    overall_rul_km:          int

    # Phase 2 classifications
    health_class:            str
    trip_readiness:          float = Field(..., ge=0, le=100)
    ml_health_score:         float = Field(..., ge=0, le=100)
    failure_flag:            int   = Field(0, ge=0, le=1)

    # Phase 3 outputs
    urgency:                 str
    maintenance_priority:    str
    book_service_within_days: int
    recommended_action:      str

    # Critical component identification
    critical_component:      Optional[str] = None

    # Component states (nested)
    engine:  EngineState
    battery: BatteryState
    fuel:    FuelState
    brake:   BrakeState

    last_updated: str


# ---------------------------------------------------------------------------
# History entry (one row per update cycle)
# ---------------------------------------------------------------------------

class HistoryEntry(BaseModel):
    """Single timestamped history entry stored in the twin's ring buffer."""
    model_config = ConfigDict(from_attributes=True)

    timestamp:       str
    engine_health:   float
    battery_health:  float
    fuel_health:     float
    brake_health:    float
    vehicle_health:  float
    failure_probability: float
    rul_cycles:      int
    rul_km:          int
    temperature:     float
    rpm:             float
    battery_voltage: float


# ---------------------------------------------------------------------------
# Simulation models
# ---------------------------------------------------------------------------

class SimulationRequest(BaseModel):
    """Request body for POST /digital_twin/simulate."""
    vehicle_id: str = Field(..., description="Vehicle ID to simulate (e.g. Vehicle_0001)")
    days:       int = Field(..., ge=1, le=365, description="Simulation horizon in days")


class SimulationDataPoint(BaseModel):
    """One day of projected vehicle state."""
    day:                int
    date:               str
    engine_health:      float
    battery_health:     float
    fuel_health:        float
    brake_health:       float
    vehicle_health:     float
    failure_probability: float
    rul_cycles:         int
    rul_km:             int
    maintenance_status: str


class SimulationResult(BaseModel):
    """Full simulation result returned by POST /digital_twin/simulate."""
    vehicle_id:         str
    simulation_days:    int
    generated_at:       str
    baseline_health:    float
    projected_failure_day: Optional[int] = None
    trajectory:         List[SimulationDataPoint]


# ---------------------------------------------------------------------------
# Risk summary
# ---------------------------------------------------------------------------

class RiskSummary(BaseModel):
    """Failure risk digest for a vehicle."""
    model_config = ConfigDict(from_attributes=True)

    vehicle_id:             str
    timestamp:              str
    failure_probability:    float = Field(..., ge=0, le=1)
    failure_risk_percentage: str
    urgency:                str
    top_risk_sensor:        Optional[str]
    top_risk_shap_value:    Optional[float]
    affected_system:        Optional[str]
    book_service_within_days: int
    maintenance_priority:   str
    recommended_action:     str
    reason:                 Optional[str]


# ---------------------------------------------------------------------------
# RUL summary
# ---------------------------------------------------------------------------

class RULSummary(BaseModel):
    """Remaining Useful Life digest for a vehicle."""
    model_config = ConfigDict(from_attributes=True)

    vehicle_id:    str
    timestamp:     str
    rul_cycles:    int
    rul_km:        int
    urgency:       str
    health_class:  str


# ---------------------------------------------------------------------------
# Paginated list wrappers
# ---------------------------------------------------------------------------

class PaginatedVehicles(BaseModel):
    total:    int
    page:     int
    per_page: int
    items:    List[VehicleState]


class PaginatedHistory(BaseModel):
    vehicle_id: str
    total:      int
    page:       int
    per_page:   int
    items:      List[HistoryEntry]


# ---------------------------------------------------------------------------
# API health-check response
# ---------------------------------------------------------------------------

class HealthCheck(BaseModel):
    status:         str = "ok"
    version:        str = "1.0.0"
    vehicles_loaded: int
    timestamp:      str
