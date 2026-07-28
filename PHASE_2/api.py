"""
api.py
======
Vehicle Health Intelligence Engine - Health Score API (Phase 2).

Fills the roadmap deliverable that the original notebook-only
implementation never produced: a callable "Health score API".

Endpoints
---------
GET  /health                        Service liveness check
POST /score                         Compute health scores for one sensor reading
GET  /fleet/summary                 Aggregate stats over the reference fleet (Output.csv)
GET  /fleet/vehicle/{index}         A single reference-fleet row, rescored live

Run with:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
Then visit http://localhost:8000/docs for interactive Swagger UI.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.config import CLASSIFIER_MODEL_PATH, DATA_DIR, REGRESSOR_MODEL_PATH
from src.health_scoring import add_all_health_scores
from src.train_classifier import get_feature_columns
from src.train_regressor import prepare_rul_target

app = FastAPI(
    title="Vehicle Health Intelligence Engine — Health Score API",
    description="Rule-based engine/battery/vehicle health scoring plus "
                "ML-derived health score and remaining-useful-life estimates.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Lazy-loaded artefacts
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _get_classifier():
    if not Path(CLASSIFIER_MODEL_PATH).exists():
        return None
    return joblib.load(CLASSIFIER_MODEL_PATH)


@lru_cache(maxsize=1)
def _get_regressor():
    if not Path(REGRESSOR_MODEL_PATH).exists():
        return None
    return joblib.load(REGRESSOR_MODEL_PATH)


@lru_cache(maxsize=1)
def _get_reference_fleet() -> pd.DataFrame:
    path = DATA_DIR / "Output.csv"
    if not path.exists():
        raise FileNotFoundError(f"Reference fleet data not found at {path}")
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SensorReading(BaseModel):
    temperature: float = Field(..., description="Engine temperature (°C)")
    pressure: float = Field(..., description="Oil/engine pressure (PSI)")
    rpm: float = Field(..., ge=0, description="Engine RPM")
    vibration: float = Field(..., ge=0, description="Vibration amplitude (g)")
    battery_voltage: float = Field(..., description="Battery voltage (V)")
    battery_current: float = Field(..., ge=0, description="Battery current draw (A)")
    battery_temp: float = Field(..., description="Battery temperature (°C)")
    fault_count: int = Field(..., ge=0, description="Number of active fault codes")


class HealthScoreResponse(BaseModel):
    engine_health: float
    battery_health: float
    vehicle_health: float
    health_class: str
    health_class_id: int
    trip_readiness: float
    trip_readiness_label: str
    ml_health_score: Optional[float] = Field(
        None, description="ML-derived health score (100 = low failure risk). "
                           "Null if no trained classifier is available."
    )
    predicted_rul: Optional[float] = Field(
        None, description="Predicted remaining useful life (arbitrary cycle units). "
                           "Null if no trained regressor is available."
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "classifier_loaded": _get_classifier() is not None,
        "regressor_loaded": _get_regressor() is not None,
    }


@app.post("/score", response_model=HealthScoreResponse)
def score_reading(reading: SensorReading):
    """Compute rule-based health scores (and ML score/RUL, if models are
    available) for a single live sensor reading."""
    df = pd.DataFrame([reading.model_dump()])
    scored = add_all_health_scores(df)
    row = scored.iloc[0]

    ml_health_score = None
    clf = _get_classifier()
    if clf is not None:
        feature_cols = get_feature_columns(scored)
        proba_failure = clf.predict_proba(scored[feature_cols].values)[:, 1][0]
        ml_health_score = float((100 * (1 - proba_failure)))

    predicted_rul = None
    reg = _get_regressor()
    if reg is not None:
        # RUL regressor was trained with an extra "RUL"/"RUL_synthetic"
        # exclusion beyond the classifier's feature set; reuse the same
        # helper so the feature order always matches what the model saw.
        rul_ready = prepare_rul_target(scored)
        from src.train_classifier import _EXCLUDE
        rul_exclude = _EXCLUDE | {"RUL", "RUL_synthetic"}
        feature_cols = [c for c in rul_ready.select_dtypes(include="number").columns if c not in rul_exclude]
        predicted_rul = float(reg.predict(rul_ready[feature_cols].values)[0])

    return HealthScoreResponse(
        engine_health=round(float(row["engine_health"]), 2),
        battery_health=round(float(row["battery_health"]), 2),
        vehicle_health=round(float(row["vehicle_health"]), 2),
        health_class=row["health_class"],
        health_class_id=int(row["health_class_id"]),
        trip_readiness=round(float(row["trip_readiness"]), 2),
        trip_readiness_label=row["trip_readiness_label"],
        ml_health_score=round(ml_health_score, 2) if ml_health_score is not None else None,
        predicted_rul=round(predicted_rul, 2) if predicted_rul is not None else None,
    )


@app.get("/fleet/summary")
def fleet_summary():
    """Aggregate health statistics across the reference fleet (Output.csv)."""
    try:
        df = _get_reference_fleet()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        "total_vehicles": len(df),
        "mean_vehicle_health": round(float(df["vehicle_health"].mean()), 2),
        "mean_engine_health": round(float(df["engine_health"].mean()), 2),
        "mean_battery_health": round(float(df["battery_health"].mean()), 2),
        "health_class_counts": df["health_class"].value_counts().to_dict(),
        "failure_rate": round(float(df["failure"].mean()), 4),
    }


@app.get("/fleet/vehicle/{index}", response_model=HealthScoreResponse)
def fleet_vehicle(index: int):
    """Re-score a single reference-fleet row (by row index) live, exercising
    the exact same code path as /score against real sensor values."""
    try:
        df = _get_reference_fleet()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if index < 0 or index >= len(df):
        raise HTTPException(status_code=404, detail=f"No vehicle at index {index}. Valid range: 0-{len(df) - 1}.")

    row = df.iloc[index]
    reading = SensorReading(
        temperature=row["temperature"], pressure=row["pressure"], rpm=row["rpm"],
        vibration=row["vibration"], battery_voltage=row["battery_voltage"],
        battery_current=row["battery_current"], battery_temp=row["battery_temp"],
        fault_count=int(row["fault_count"]),
    )
    return score_reading(reading)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False, log_level="info")
