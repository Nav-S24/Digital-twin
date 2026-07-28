"""
api/main.py

Step 7: REST API for Phase 9 - Driver Behaviour Analytics.

Endpoints (as specified):
    GET /driver/profile      -> DriverProfileResponse
    GET /driver/score        -> DriverScoreResponse
    GET /driver/coaching     -> CoachingResponse
    GET /driver/statistics   -> DriverStatisticsResponse
    GET /driver/trips        -> TripListResponse

Plus supporting operational endpoints:
    POST /pipeline/run       -> load & process a VED data source
    GET  /health             -> liveness/readiness probe
    GET  /drivers             -> list all known driver ids

Run with:
    uvicorn api.main:app --host 0.0.0.0 --port 8009 --reload
"""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from config.settings import API
from models.schemas import (
    CoachingResponse, DriverProfileResponse, DriverScoreResponse,
    DriverStatisticsResponse, ErrorResponse, TripListResponse, TripSummary,
)
from pipeline import pipeline
from utils.exceptions import (
    DataLoadError, DriverBehaviorError, DriverNotFoundError, TripNotFoundError,
)
from utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(title=API.title, version=API.version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_pipeline_ready() -> None:
    if not pipeline.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Pipeline has not been run yet. Call POST /pipeline/run with a data source first.",
        )


@app.exception_handler(DriverNotFoundError)
async def driver_not_found_handler(request, exc: DriverNotFoundError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": str(exc), "error_type": "DriverNotFoundError"})


@app.exception_handler(TripNotFoundError)
async def trip_not_found_handler(request, exc: TripNotFoundError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": str(exc), "error_type": "TripNotFoundError"})


@app.exception_handler(DriverBehaviorError)
async def generic_driver_behavior_error_handler(request, exc: DriverBehaviorError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=400, content={"detail": str(exc), "error_type": type(exc).__name__})


@app.get("/health")
def health():
    """Liveness/readiness probe."""
    return {"status": "ok", "pipeline_ready": pipeline.is_ready()}


@app.post("/pipeline/run")
def run_pipeline(source: str = Query(..., description="Path to a VED CSV file or directory of CSVs")):
    """
    Load and process a VED data source (CSV file path or directory).
    Must be called once before the /driver/* endpoints will work.
    """
    try:
        pipeline.run(source)
    except DataLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "success",
        "trips_processed": int(len(pipeline.scored_trips_df)),
        "drivers": int(pipeline.scored_trips_df["veh_id"].nunique()),
        "events_detected": int(len(pipeline.events_df)),
    }


@app.get("/drivers")
def list_drivers():
    """List all driver (veh_id) values currently loaded in the pipeline."""
    _require_pipeline_ready()
    ids = sorted(pipeline.scored_trips_df["veh_id"].unique().tolist())
    return {"driver_count": len(ids), "veh_ids": ids}


@app.get("/driver/profile", response_model=DriverProfileResponse)
def get_driver_profile(veh_id: int = Query(..., description="Vehicle / driver ID")):
    """Return the driver's overall behaviour profile category."""
    _require_pipeline_ready()
    profile = pipeline.get_driver_profile(veh_id)
    return DriverProfileResponse(**profile)


@app.get("/driver/score", response_model=DriverScoreResponse)
def get_driver_score(veh_id: int = Query(..., description="Vehicle / driver ID")):
    """Return the driver's distance-weighted aggregate 0-100 score with real penalty/bonus totals."""
    _require_pipeline_ready()
    detail = pipeline.get_driver_score_detail(veh_id)
    return DriverScoreResponse(
        veh_id=veh_id, driver_score=detail["driver_score"],
        total_penalty=detail["total_penalty"], total_bonus=detail["total_bonus"],
    )


@app.get("/driver/coaching", response_model=CoachingResponse)
def get_driver_coaching(
    veh_id: int = Query(..., description="Vehicle / driver ID"),
    global_trip_id: Optional[str] = Query(None, description="Specific trip; defaults to lowest-scoring trip"),
    use_llm: bool = Query(True, description="Attempt LLM-generated narrative"),
):
    """Return coaching recommendations for a driver (or a specific trip)."""
    _require_pipeline_ready()
    if global_trip_id:
        result = pipeline.get_trip_coaching(global_trip_id, use_llm=use_llm)
    else:
        result = pipeline.get_driver_coaching(veh_id, use_llm=use_llm)
    return CoachingResponse(veh_id=veh_id, global_trip_id=global_trip_id, **result)


@app.get("/driver/statistics", response_model=DriverStatisticsResponse)
def get_driver_statistics(veh_id: int = Query(..., description="Vehicle / driver ID")):
    """Return aggregated driving statistics for a driver."""
    _require_pipeline_ready()
    stats = pipeline.get_driver_statistics(veh_id)
    return DriverStatisticsResponse(**stats)


@app.get("/driver/trips", response_model=TripListResponse)
def get_driver_trips(veh_id: int = Query(..., description="Vehicle / driver ID")):
    """Return a list of all trips for a driver with per-trip score/profile."""
    _require_pipeline_ready()
    trips_df = pipeline.list_driver_trips(veh_id)
    trips = [
        TripSummary(
            global_trip_id=row["global_trip_id"], veh_id=int(row["veh_id"]),
            trip_id=int(row["trip_id"]), trip_start_time=row["trip_start_time"],
            driver_score=float(row["driver_score"]), driver_profile=row["driver_profile"],
            distance_travelled_km=float(row["distance_travelled_km"]),
            trip_duration_s=float(row["trip_duration_s"]),
        )
        for _, row in trips_df.iterrows()
    ]
    return TripListResponse(veh_id=veh_id, trip_count=len(trips), trips=trips)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host=API.host, port=API.port, reload=True)
