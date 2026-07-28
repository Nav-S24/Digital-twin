"""
app.py
Phase 8 - Trip Intelligence Module

FastAPI service exposing the Trip Readiness Assessment as a REST API.
Run with:
    uvicorn app:app --reload --port 8008

Endpoints:
    GET  /health                       -> service liveness check
    GET  /vehicles                     -> list vehicle IDs available from Phase 3 output
    POST /trip/assess                  -> full trip readiness assessment (TripRequest -> TripResponse)
    POST /trip/assess/by_vehicle_id    -> convenience endpoint using Phase 3/5 integration
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from api.schemas import TripRequest, TripResponse
from config import settings
from data_loader import VehicleDataLoader
from trip_engine import TripOrchestrator
from utils import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title=settings.app_name,
    description="Trip Readiness Assessment combining vehicle health, failure risk, "
                "digital twin status, route, weather, driver behaviour, and fuel economics. "
                "Responses now also include prioritized recommendations, a service centre "
                "recommendation (when applicable), an alternate route suggestion (when "
                "applicable), and an explainable-AI breakdown of the GO/CAUTION/NO-GO decision.",
    version="1.1.0",
)

orchestrator = TripOrchestrator()
loader = VehicleDataLoader()


class QuickTripRequest(BaseModel):
    vehicle_id: str
    source: str
    destination: str
    fuel_level_l: float = 30.0
    mileage_kmpl: Optional[float] = None
    tank_capacity_l: Optional[float] = None
    active_dtc_codes: Optional[List[str]] = None
    fuel_type: str = "petrol"
    driver_behaviour_score: Optional[float] = None  # NEW: 0-100, higher = safer driving


@app.get("/health")
def health_check():
    return {"status": "ok", "service": settings.app_name}


@app.get("/vehicles")
def list_vehicles():
    ids = loader.list_vehicle_ids()
    return {"count": len(ids), "vehicle_ids": ids[:200]}  # cap payload size


@app.post("/trip/assess", response_model=TripResponse)
def assess_trip(request: TripRequest):
    try:
        return orchestrator.assess_trip(request)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Trip assessment failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Trip assessment failed: {exc}") from exc


@app.post("/trip/assess/by_vehicle_id", response_model=TripResponse)
def assess_trip_by_vehicle_id(request: QuickTripRequest):
    """Convenience endpoint: pulls vehicle health/failure data from Phase 3/5
    outputs by vehicle_id instead of requiring the caller to supply it."""
    try:
        vehicle = loader.get_vehicle_state(
            vehicle_id=request.vehicle_id,
            fuel_level_l=request.fuel_level_l,
            mileage_kmpl=request.mileage_kmpl,
            tank_capacity_l=request.tank_capacity_l,
            active_dtc_codes=request.active_dtc_codes,
            driver_behaviour_score=request.driver_behaviour_score,
        )
        trip_request = TripRequest(
            vehicle=vehicle,
            source=request.source,
            destination=request.destination,
            fuel_type=request.fuel_type,
        )
        return orchestrator.assess_trip(trip_request)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Trip assessment (by vehicle_id) failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Trip assessment failed: {exc}") from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8008, reload=True)
