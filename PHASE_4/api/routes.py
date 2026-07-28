"""
api/routes.py
=============
FastAPI route handlers for the Vehicle Digital Twin REST API.

All endpoints are read-only (GET) except POST /digital_twin/simulate.
Route handlers are thin — they delegate all business logic to the
Synchronizer and SimulationEngine services.

Endpoint summary
----------------
GET  /                              Health check
GET  /digital_twin/fleet            Fleet-level aggregate statistics
GET  /digital_twin/vehicles         Paginated list of all vehicle states
GET  /digital_twin/current/{id}     Complete vehicle twin state
GET  /digital_twin/components/{id}  All four component states
GET  /digital_twin/history/{id}     Historical trend data
GET  /digital_twin/risk/{id}        Failure risk digest
GET  /digital_twin/rul/{id}         Remaining Useful Life digest
POST /digital_twin/simulate         Future degradation simulation
GET  /digital_twin/refresh          Force reload of CSV data
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from services.simulation_engine import SimulationEngine, get_simulation_engine
from services.synchronizer import Synchronizer, get_synchronizer
from utils.helpers import utc_now_iso
from utils.models import SimulationRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/digital_twin", tags=["Digital Twin"])


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _require_twin(vehicle_id: str, sync: Synchronizer) -> Any:
    """Raise 404 if the vehicle is not found in the registry."""
    twin = sync.get_twin(vehicle_id)
    if not twin:
        raise HTTPException(
            status_code=404,
            detail=f"Vehicle '{vehicle_id}' not found. "
                   f"Valid IDs range from Vehicle_0001 to Vehicle_2000.",
        )
    return twin


# ---------------------------------------------------------------------------
# System routes
# ---------------------------------------------------------------------------

@router.get("/health", tags=["System"])
async def health_check(sync: Synchronizer = Depends(get_synchronizer)) -> Dict:
    """API health check — confirms the twin registry is loaded."""
    return {
        "status":          "ok",
        "version":         "1.0.0",
        "vehicles_loaded": sync.total_vehicles,
        "ready":           sync.is_ready,
        "timestamp":       utc_now_iso(),
    }


@router.get("/refresh", tags=["System"])
async def refresh_data(sync: Synchronizer = Depends(get_synchronizer)) -> Dict:
    """
    Force a reload of Phase 2 and Phase 3 CSV files and re-synchronise
    all twin instances.  Use after updating the CSV outputs.
    """
    try:
        sync.refresh()
        return {
            "status":    "refreshed",
            "vehicles":  sync.total_vehicles,
            "timestamp": utc_now_iso(),
        }
    except Exception as exc:
        logger.error("Refresh failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Refresh failed: {exc}")


# ---------------------------------------------------------------------------
# Fleet-level routes
# ---------------------------------------------------------------------------

@router.get("/fleet")
async def get_fleet_summary(sync: Synchronizer = Depends(get_synchronizer)) -> Dict:
    """
    Return aggregate fleet statistics:
    - vehicle counts by health class
    - mean health and failure probability
    - service urgency counts
    """
    return sync.fleet_summary()


@router.get("/vehicles")
async def list_vehicles(
    page:         int           = Query(1,  ge=1,  description="Page number"),
    per_page:     int           = Query(50, ge=1, le=500, description="Items per page"),
    health_class: Optional[str] = Query(None, description="Filter: Excellent|Good|Warning|Critical"),
    urgency:      Optional[str] = Query(None, description="Filter: LOW|MEDIUM|CRITICAL"),
    sort_by:      str           = Query("overall_health", description="Sort field"),
    ascending:    bool          = Query(True, description="Sort direction"),
    sync:         Synchronizer  = Depends(get_synchronizer),
) -> Dict:
    """
    Paginated, filterable list of all vehicle states.

    Supports filtering by health_class and urgency, and sorting by
    overall_health, vehicle_id, failure_probability, or book_service_within_days.
    """
    return sync.get_all_states(
        page=page,
        per_page=per_page,
        health_class=health_class,
        urgency=urgency,
        sort_by=sort_by,
        ascending=ascending,
    )


# ---------------------------------------------------------------------------
# Per-vehicle routes
# ---------------------------------------------------------------------------

@router.get("/current/{vehicle_id}")
async def get_current_state(
    vehicle_id: str,
    sync: Synchronizer = Depends(get_synchronizer),
) -> Dict:
    """
    Return the complete current Digital Twin state for a single vehicle.

    Includes:
    - Overall vehicle health, failure probability, RUL
    - Phase 2 classifications (health_class, trip_readiness)
    - Phase 3 predictions (urgency, recommended_action, book_within_days)
    - All four component twin states (engine, battery, fuel, brake)
    """
    twin = _require_twin(vehicle_id, sync)
    return twin.to_dict()


@router.get("/components/{vehicle_id}")
async def get_component_states(
    vehicle_id: str,
    sync: Synchronizer = Depends(get_synchronizer),
) -> Dict:
    """
    Return the state of all four component twins for a single vehicle.

    Useful for the Component Health dashboard page.
    """
    result = sync.get_component_states(vehicle_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Vehicle '{vehicle_id}' not found.")
    return result


@router.get("/history/{vehicle_id}")
async def get_history(
    vehicle_id: str,
    page:       int = Query(1,  ge=1),
    per_page:   int = Query(50, ge=1, le=500),
    sync: Synchronizer = Depends(get_synchronizer),
) -> Dict:
    """
    Return paginated historical trend data for a vehicle.

    Each history entry contains health scores, sensor readings, failure
    probability, and RUL at each synchronisation timestep.

    Note: history accumulates only within the current server session.
    Historical data from the CSV (pre-startup) is loaded as a single
    initial snapshot per vehicle.
    """
    _require_twin(vehicle_id, sync)
    history = sync.get_history(vehicle_id)
    if history is None:
        raise HTTPException(status_code=404, detail=f"Vehicle '{vehicle_id}' not found.")

    total = len(history)
    start = (page - 1) * per_page
    end   = start + per_page

    return {
        "vehicle_id": vehicle_id,
        "total":      total,
        "page":       page,
        "per_page":   per_page,
        "items":      history[start:end],
    }


@router.get("/risk/{vehicle_id}")
async def get_risk_summary(
    vehicle_id: str,
    sync: Synchronizer = Depends(get_synchronizer),
) -> Dict:
    """
    Return the failure risk digest for a vehicle.

    Includes failure probability, urgency, SHAP explanation, top risk sensor,
    affected system, and maintenance recommendation.
    """
    _require_twin(vehicle_id, sync)
    result = sync.get_risk_summary(vehicle_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Vehicle '{vehicle_id}' not found.")
    return result


@router.get("/rul/{vehicle_id}")
async def get_rul_summary(
    vehicle_id: str,
    sync: Synchronizer = Depends(get_synchronizer),
) -> Dict:
    """
    Return the Remaining Useful Life (RUL) digest for a vehicle.

    Returns both cycle-based and km-based RUL along with the current
    health class and urgency label.
    """
    _require_twin(vehicle_id, sync)
    result = sync.get_rul_summary(vehicle_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Vehicle '{vehicle_id}' not found.")
    return result


# ---------------------------------------------------------------------------
# Simulation route
# ---------------------------------------------------------------------------

@router.post("/simulate")
async def run_simulation(
    request: SimulationRequest,
    sync:    Synchronizer    = Depends(get_synchronizer),
    sim_eng: SimulationEngine = Depends(get_simulation_engine),
) -> Dict:
    """
    Run a future degradation simulation for the specified vehicle.

    Request body
    ------------
    ```json
    { "vehicle_id": "Vehicle_0001", "days": 90 }
    ```

    Response
    --------
    Full SimulationResult including:
    - Baseline health at time of simulation
    - Projected failure day (first day vehicle health drops below 40)
    - Day-by-day trajectory for engine, battery, fuel, brake, and vehicle health
    - Failure probability and RUL projections per day
    - Maintenance status per day

    Supported horizons: 30, 60, 90, 180, 365 days (any value 1–365 is accepted).
    """
    twin = _require_twin(request.vehicle_id, sync)

    try:
        result = sim_eng.run(twin, request.days)
        return result.model_dump()
    except Exception as exc:
        logger.error("Simulation error for %s: %s", request.vehicle_id, exc)
        raise HTTPException(status_code=500, detail=f"Simulation failed: {exc}")


# ---------------------------------------------------------------------------
# Convenience: list all vehicle IDs
# ---------------------------------------------------------------------------

@router.get("/ids")
async def list_ids(sync: Synchronizer = Depends(get_synchronizer)) -> Dict:
    """Return a sorted list of all Vehicle_IDs loaded in the registry."""
    return {
        "count":       sync.total_vehicles,
        "vehicle_ids": sync.list_vehicle_ids(),
    }
